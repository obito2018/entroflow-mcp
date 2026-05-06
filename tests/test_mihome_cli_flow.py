# -*- coding: utf-8 -*-
import argparse
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import cli  # noqa: E402
from core import config, downloader, loader, store  # noqa: E402
from tools import system as system_tools  # noqa: E402


class NonInteractiveStdin:
    def isatty(self) -> bool:
        return False


class FakeConnector:
    def __init__(
        self,
        poll_results: list[dict],
        devices: list[dict] | None = None,
        file_path: str | None = None,
        public_url: str | None = None,
    ):
        self._poll_results = list(poll_results)
        self._devices = devices or []
        self._file_path = file_path
        self._public_url = public_url
        self.poll_calls = 0
        self.contexts: list[dict] = []

    def connect(self, context: dict) -> dict:
        self.contexts.append(dict(context))
        actions = [
            {
                "type": "scan_qr",
                "url": "https://example.com/login",
                "message": "Scan this code with the platform app.",
            }
        ]
        if self._public_url:
            actions[0]["public_url"] = self._public_url
        if context.get("presentation") == "file" and self._file_path:
            actions.append(
                {
                    "type": "open_file",
                    "file_path": self._file_path,
                    "message": "Send this file to the user through chat or open it on another device.",
                }
            )
        return {
            "status": "pending",
            "session_id": "session-1",
            "expires_in": 120,
            "message": "Complete the connector-provided connection action.",
            "actions": actions,
        }

    def poll_connect(self, session_id: str, context: dict) -> dict:
        result = self._poll_results[min(self.poll_calls, len(self._poll_results) - 1)]
        self.poll_calls += 1
        return result

    def list_devices(self) -> list[dict]:
        return list(self._devices)


class FakeTokenConnector:
    def __init__(self):
        self.calls: list[dict] = []

    def connect(self, context: dict) -> dict:
        self.calls.append(dict(context.get("inputs") or {}))
        inputs = context.get("inputs") or {}
        if not inputs.get("url") or not inputs.get("token"):
            return {
                "status": "requires_input",
                "message": "Home Assistant needs a URL and long-lived access token.",
                "required_inputs": [
                    {"name": "url", "description": "Home Assistant base URL"},
                    {"name": "token", "description": "Home Assistant long-lived access token", "secret": True},
                ],
            }
        return {
            "status": "connected",
            "message": "Home Assistant connected successfully.",
        }



class MihomeCliFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.home = Path(self.temp_dir.name) / ".entroflow"
        self.assets_dir = self.home / "assets"
        self.docs_dir = self.home / "docs" / "platforms"
        self.runtime_dir = self.home / "runtime"
        self.config_path = self.home / "config.json"
        self.store_path = self.home / "data" / "devices.json"
        self.bundled_catalog_path = Path(self.temp_dir.name) / "bundled_catalog.json"
        self.bundled_catalog_path.write_text(
            json.dumps(
                {
                    "platforms": [
                        {
                            "id": "mihome",
                            "display_name": "Xiaomi IoT",
                            "aliases": ["mihome", "xiaomi"],
                        }
                    ]
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        self.patches = [
            patch.object(cli, "ASSETS_DIR", self.assets_dir),
            patch.object(cli, "PLATFORM_DOCS_DIR", self.docs_dir),
            patch.object(cli, "BUNDLED_CATALOG_PATH", self.bundled_catalog_path),
            patch.object(config, "CONFIG_PATH", self.config_path),
            patch.object(config, "ASSETS_DIR", self.assets_dir),
            patch.object(downloader, "ASSETS_DIR", self.assets_dir),
            patch.object(downloader, "CATALOG_PATH", self.assets_dir / "catalog.json"),
            patch.object(downloader, "PLATFORM_DOCS_DIR", self.docs_dir),
            patch.object(loader, "ASSETS_DIR", self.assets_dir),
            patch.object(loader, "RUNTIME_DIR", self.runtime_dir),
            patch.object(store, "STORE_PATH", self.store_path),
            patch.object(system_tools, "ASSETS_DIR", self.assets_dir),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

        loader._module_cache.clear()
        self.addCleanup(loader._module_cache.clear)

    def _write_connector_client(self, platform: str, body: str = "VALUE = 1\n") -> Path:
        client_path = self._connector_dir(platform) / "client.py"
        client_path.write_text(body, encoding="utf-8")
        return client_path

    def _connector_dir(self, platform: str) -> Path:
        path = self.assets_dir / platform / "connector"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _devices_file(self, platform: str) -> Path:
        return self._connector_dir(platform) / f"{platform}_devices.json"

    def _write_platform_devices(self, platform: str, models: list[str]) -> Path:
        devices_path = self._devices_file(platform)
        devices_path.write_text(
            json.dumps([{"model": model} for model in models], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return devices_path

    def test_connect_mihome_skips_input_when_stdin_is_not_tty(self):
        self._write_platform_devices("mihome", ["old.model"])
        connector = FakeConnector(
            poll_results=[
                {"status": "waiting", "message": "Waiting for confirmation..."},
                {"status": "ok"},
            ]
        )
        printed: list[str] = []

        with (
            patch.object(cli, "_refresh_catalog"),
            patch.object(cli, "_resolve_platform_or_exit", return_value="mihome"),
            patch.object(downloader, "download_platform_guide", return_value=None),
            patch.object(downloader, "refresh_platform_devices_file", return_value={
                "platform_id": "mihome",
                "path": str(self._devices_file("mihome")),
                "count": 12263,
            }),
            patch.object(loader, "load_connector", return_value=connector),
            patch.object(cli, "_open_browser", return_value=False),
            patch.object(cli, "_print", side_effect=printed.append),
            patch("builtins.input", side_effect=AssertionError("input() should not be called")),
            patch.object(sys, "stdin", NonInteractiveStdin()),
            patch.object(time, "sleep", return_value=None),
        ):
            rc = cli.cmd_connect(argparse.Namespace(platform="mihome", no_prompt=False, presentation="auto", input=[], timeout=600, url=None, token=None))

        self.assertEqual(rc, 0)
        self.assertEqual(connector.poll_calls, 2)
        self.assertIn("Non-interactive mode detected; waiting for the connector to report connection status...", printed)

    def test_connect_mihome_file_presentation_prints_local_file_and_skips_browser(self):
        self._write_platform_devices("mihome", ["old.model"])
        qr_file = str(self.runtime_dir / "mihome-login-session-1.png")
        connector = FakeConnector(
            poll_results=[
                {"status": "waiting", "message": "Waiting for confirmation..."},
                {"status": "ok"},
            ],
            file_path=qr_file,
            public_url="https://api.entroflow.ai/v1/tmp/login-qr/test-token",
        )
        printed: list[str] = []

        with (
            patch.object(cli, "_refresh_catalog"),
            patch.object(cli, "_resolve_platform_or_exit", return_value="mihome"),
            patch.object(downloader, "download_platform_guide", return_value=None),
            patch.object(downloader, "refresh_platform_devices_file", return_value={
                "platform_id": "mihome",
                "path": str(self._devices_file("mihome")),
                "count": 12263,
            }),
            patch.object(loader, "load_connector", return_value=connector),
            patch.object(cli, "_open_browser", side_effect=AssertionError("_open_browser() should not be called")),
            patch.object(cli, "_print", side_effect=printed.append),
            patch("builtins.input", side_effect=AssertionError("input() should not be called")),
            patch.object(sys, "stdin", NonInteractiveStdin()),
            patch.object(time, "sleep", return_value=None),
        ):
            rc = cli.cmd_connect(argparse.Namespace(platform="mihome", no_prompt=False, presentation="file", input=[], timeout=600, url=None, token=None))

        self.assertEqual(rc, 0)
        joined = "\n".join(printed)
        self.assertIn("Send this file to the user through chat or open it on another device.", joined)
        self.assertIn(qr_file, joined)
        self.assertIn("https://api.entroflow.ai/v1/tmp/login-qr/test-token", joined)
        self.assertIn("https://example.com/login", joined)

    def test_connect_rejects_connector_without_v2_connect(self):
        self._write_platform_devices("mihome", ["old.model"])

        class LegacyConnector:
            pass

        with (
            patch.object(cli, "_refresh_catalog"),
            patch.object(cli, "_resolve_platform_or_exit", return_value="mihome"),
            patch.object(downloader, "download_platform_guide", return_value=None),
            patch.object(downloader, "refresh_platform_devices_file", return_value={
                "platform_id": "mihome",
                "path": str(self._devices_file("mihome")),
                "count": 12263,
            }),
            patch.object(loader, "load_connector", return_value=LegacyConnector()),
            patch.object(sys, "stdin", NonInteractiveStdin()),
        ):
            with self.assertRaisesRegex(RuntimeError, "connector protocol v2"):
                cli.cmd_connect(argparse.Namespace(platform="mihome", no_prompt=False, presentation="auto", input=[], timeout=600, url=None, token=None))

    def test_update_refreshes_platform_device_table_even_without_platform_version_change(self):
        config.set_platform_version("mihome", "1.0.3")
        config.add_connected_iot_platform("mihome")
        devices_path = self._write_platform_devices("mihome", [f"legacy.model.{idx}" for idx in range(303)])
        latest_payload = [{"model": f"mihome.model.{idx}"} for idx in range(12263)]
        printed: list[str] = []

        def refresh_side_effect(platform: str) -> dict:
            self.assertEqual(platform, "mihome")
            devices_path.write_text(
                json.dumps(latest_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return {
                "platform_id": platform,
                "path": str(devices_path),
                "count": len(latest_payload),
            }

        with (
            patch.object(cli, "_print", side_effect=printed.append),
            patch.object(cli, "check_updates", return_value="Checking updates:\n  platform mihome: 1.0.3 (up to date)"),
            patch.object(cli, "update_server", return_value="MCP Server is already up to date (1.0.3)."),
            patch.object(downloader, "refresh_catalog", return_value={}),
            patch.object(downloader, "refresh_platform_devices_file", side_effect=refresh_side_effect),
            patch.object(downloader, "refresh_platform_guides", return_value=[]),
        ):
            rc = cli.cmd_update(argparse.Namespace())

        self.assertEqual(rc, 0)
        payload = json.loads(devices_path.read_text(encoding="utf-8"))
        self.assertEqual(len(payload), 12263)
        joined = "\n".join(printed)
        self.assertIn("Platform device tables:", joined)
        self.assertIn("mihome: refreshed 12263 models", joined)
        joined.encode("ascii")

    def test_list_devices_uses_refreshed_platform_support_table(self):
        self._write_platform_devices("mihome", ["fawad.aircondition.3010"])
        connector = FakeConnector(
            poll_results=[{"status": "ok"}],
            devices=[
                {
                    "did": "709145591",
                    "model": "fawad.aircondition.3010",
                    "name": "Bedroom AC",
                }
            ],
        )
        printed: list[str] = []

        with (
            patch.object(cli, "_refresh_catalog"),
            patch.object(cli, "_resolve_platform_or_exit", return_value="mihome"),
            patch.object(loader, "load_connector", return_value=connector),
            patch.object(cli, "_print", side_effect=printed.append),
        ):
            rc = cli.cmd_list_devices(argparse.Namespace(platform="mihome"))

        self.assertEqual(rc, 0)
        joined = "\n".join(printed)
        self.assertIn("support   : supported", joined)
        self.assertIn("device_id : mihome:709145591", joined)

    def test_system_update_messages_are_ascii_safe(self):
        (self.assets_dir / "mihome").mkdir(parents=True, exist_ok=True)
        config.set_platform_version("mihome", "1.0.3")
        config.set_server_version("1.0.3")

        with patch.object(downloader, "get_platform_latest_version", return_value="1.0.3"):
            update_text = system_tools.check_updates()

        with patch.object(downloader, "get_server_latest_version", return_value="1.0.3"):
            server_text = system_tools.update_server()

        update_text.encode("ascii")
        server_text.encode("ascii")

    def test_update_ignores_agent_platform_entries(self):
        config.set_installed_platforms(["Codex", "OpenClaw"])
        config.add_connected_iot_platform("mihome")
        config.set_platform_version("mihome", "1.0.4")
        self._write_connector_client("mihome")
        self._write_platform_devices("mihome", ["mihome.model.1"])

        refresh_calls: list[str] = []

        with (
            patch.object(cli, "_print"),
            patch.object(cli, "update_server", return_value="MCP Server is already up to date (1.0.4)."),
            patch.object(downloader, "refresh_catalog", return_value={}),
            patch.object(downloader, "get_platform_latest_version", return_value="1.0.4"),
            patch.object(downloader, "refresh_platform_devices_file", side_effect=lambda platform: refresh_calls.append(platform) or {
                "platform_id": platform,
                "path": str(self._devices_file(platform)),
                "count": 1,
            }),
            patch.object(downloader, "refresh_platform_guides", return_value=[]),
        ):
            rc = cli.cmd_update(argparse.Namespace())

        self.assertEqual(rc, 0)
        self.assertEqual(refresh_calls, ["mihome"])

    def test_update_repairs_platform_when_version_metadata_is_missing(self):
        config.set_installed_platforms(["Codex"])
        config.add_connected_iot_platform("mihome")
        self._write_connector_client("mihome")
        self._write_platform_devices("mihome", ["legacy.model"])
        printed: list[str] = []

        def download_platform_side_effect(platform: str) -> str:
            self.assertEqual(platform, "mihome")
            self._write_connector_client("mihome", "VALUE = 2\n")
            self._write_platform_devices("mihome", ["mihome.model.0"])
            return "1.0.4"

        with (
            patch.object(cli, "_print", side_effect=printed.append),
            patch.object(cli, "update_server", return_value="MCP Server is already up to date (1.0.4)."),
            patch.object(downloader, "refresh_catalog", return_value={}),
            patch.object(downloader, "get_platform_latest_version", return_value="1.0.4"),
            patch.object(downloader, "download_platform", side_effect=download_platform_side_effect),
            patch.object(downloader, "refresh_platform_devices_file", return_value={
                "platform_id": "mihome",
                "path": str(self._devices_file("mihome")),
                "count": 1,
            }),
            patch.object(downloader, "refresh_platform_guides", return_value=[]),
        ):
            rc = cli.cmd_update(argparse.Namespace())

        self.assertEqual(rc, 0)
        self.assertEqual(config.get_platform_version("mihome"), "1.0.4")
        joined = "\n".join(printed)
        self.assertIn("missing version metadata", joined)

    def test_connect_updates_platform_connector_when_local_version_is_stale(self):
        config.set_platform_version("mihome", "1.0.3")
        config.add_connected_iot_platform("mihome")
        self._write_connector_client("mihome", "VALUE = 1\n")
        self._write_platform_devices("mihome", ["legacy.model"])
        connector = FakeConnector(
            poll_results=[
                {"status": "ok"},
            ]
        )
        printed: list[str] = []

        def download_platform_side_effect(platform: str) -> str:
            self.assertEqual(platform, "mihome")
            self._write_connector_client("mihome", "VALUE = 2\n")
            self._write_platform_devices("mihome", ["mihome.model.0"])
            return "1.0.4"

        with (
            patch.object(cli, "_refresh_catalog"),
            patch.object(cli, "_resolve_platform_or_exit", return_value="mihome"),
            patch.object(downloader, "download_platform_guide", return_value=None),
            patch.object(downloader, "get_platform_latest_version", return_value="1.0.4"),
            patch.object(downloader, "download_platform", side_effect=download_platform_side_effect),
            patch.object(downloader, "refresh_platform_devices_file", return_value={
                "platform_id": "mihome",
                "path": str(self._devices_file("mihome")),
                "count": 1,
            }),
            patch.object(loader, "load_connector", return_value=connector),
            patch.object(cli, "_open_browser", return_value=False),
            patch.object(cli, "_print", side_effect=printed.append),
            patch("builtins.input", side_effect=AssertionError("input() should not be called")),
            patch.object(sys, "stdin", NonInteractiveStdin()),
        ):
            rc = cli.cmd_connect(argparse.Namespace(platform="mihome", no_prompt=False, presentation="auto", input=[], timeout=600, url=None, token=None))

        self.assertEqual(rc, 0)
        self.assertEqual(config.get_platform_version("mihome"), "1.0.4")
        self.assertIn("Updated platform connector mihome (1.0.3 -> v1.0.4)", "\n".join(printed))

    def test_connect_homeassistant_uses_direct_token_login(self):
        config.set_platform_version("homeassistant", "1.0.1")
        config.add_connected_iot_platform("homeassistant")
        self._write_connector_client("homeassistant")
        self._write_platform_devices("homeassistant", ["ha.hue.light"])
        connector = FakeTokenConnector()
        printed: list[str] = []

        with (
            patch.object(cli, "_refresh_catalog"),
            patch.object(cli, "_resolve_platform_or_exit", return_value="homeassistant"),
            patch.object(downloader, "download_platform_guide", return_value=None),
            patch.object(downloader, "get_platform_latest_version", return_value="1.0.1"),
            patch.object(downloader, "refresh_platform_devices_file", return_value={
                "platform_id": "homeassistant",
                "path": str(self._devices_file("homeassistant")),
                "count": 1,
            }),
            patch.object(loader, "load_connector", return_value=connector),
            patch.object(cli, "_open_browser", side_effect=AssertionError("browser should not be opened")),
            patch.object(cli, "_print", side_effect=printed.append),
            patch("builtins.input", side_effect=AssertionError("input() should not be called")),
        ):
            rc = cli.cmd_connect(argparse.Namespace(
                platform="homeassistant",
                no_prompt=False,
                presentation="auto", input=[], timeout=600, url="http://ha.local:8123", token="secret-token",
            ))

        self.assertEqual(rc, 0)
        self.assertEqual(connector.calls, [{"url": "http://ha.local:8123", "token": "secret-token"}])
        self.assertIn("Home Assistant connected successfully.", "\n".join(printed))

    def test_connect_homeassistant_reports_required_inputs_without_token(self):
        config.set_platform_version("homeassistant", "1.0.1")
        config.add_connected_iot_platform("homeassistant")
        self._write_connector_client("homeassistant")
        self._write_platform_devices("homeassistant", ["ha.hue.light"])
        connector = FakeTokenConnector()

        with (
            patch.object(cli, "_refresh_catalog"),
            patch.object(cli, "_resolve_platform_or_exit", return_value="homeassistant"),
            patch.object(downloader, "download_platform_guide", return_value=None),
            patch.object(downloader, "get_platform_latest_version", return_value="1.0.1"),
            patch.object(downloader, "refresh_platform_devices_file", return_value={
                "platform_id": "homeassistant",
                "path": str(self._devices_file("homeassistant")),
                "count": 1,
            }),
            patch.object(loader, "load_connector", return_value=connector),
            patch.object(cli, "_open_browser", side_effect=AssertionError("browser should not be opened")),
            patch("builtins.input", side_effect=AssertionError("input() should not be called")),
            patch.object(sys, "stdin", NonInteractiveStdin()),
        ):
            rc = cli.cmd_connect(argparse.Namespace(
                platform="homeassistant",
                no_prompt=False,
                presentation="auto", input=[], timeout=600, url=None, token=None,
            ))

        self.assertEqual(rc, 1)

    def test_list_platforms_uses_bundled_catalog_when_local_catalog_is_missing(self):
        printed: list[str] = []

        with (
            patch.object(downloader, "refresh_catalog", side_effect=RuntimeError("offline")),
            patch.object(cli, "_print", side_effect=printed.append),
        ):
            rc = cli.cmd_list_platforms(argparse.Namespace(query=None))

        self.assertEqual(rc, 0)
        self.assertTrue((self.assets_dir / "catalog.json").exists())
        joined = "\n".join(printed)
        self.assertIn("Using the local cached catalog instead.", joined)
        self.assertIn("Found 1 supported platform(s):", joined)
        self.assertIn("- mihome (Xiaomi IoT)", joined)

    def test_list_platforms_reports_catalog_refresh_failure_and_uses_cached_catalog(self):
        (self.assets_dir).mkdir(parents=True, exist_ok=True)
        (self.assets_dir / "catalog.json").write_text(
            json.dumps(
                {
                    "platforms": [
                        {
                            "id": "mihome",
                            "display_name": "Xiaomi IoT",
                            "aliases": ["mihome"],
                        }
                    ]
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        printed: list[str] = []

        with (
            patch.object(downloader, "refresh_catalog", side_effect=RuntimeError("catalog endpoint down")),
            patch.object(cli, "_print", side_effect=printed.append),
        ):
            rc = cli.cmd_list_platforms(argparse.Namespace(query=None))

        self.assertEqual(rc, 0)
        joined = "\n".join(printed)
        self.assertIn("Platform catalog refresh failed: catalog endpoint down", joined)
        self.assertIn("Using the local cached catalog instead.", joined)

    def test_update_reports_catalog_refresh_failure_instead_of_success(self):
        config.add_connected_iot_platform("mihome")
        config.set_platform_version("mihome", "1.0.4")
        self._write_connector_client("mihome")
        self._write_platform_devices("mihome", ["mihome.model.1"])
        printed: list[str] = []

        with (
            patch.object(cli, "_print", side_effect=printed.append),
            patch.object(downloader, "refresh_catalog", side_effect=RuntimeError("catalog endpoint down")),
            patch.object(cli, "check_updates", return_value="Checking updates:\n\nAll packages are up to date."),
            patch.object(cli, "update_server", return_value="MCP Server is already up to date (1.0.2)."),
            patch.object(downloader, "refresh_platform_devices_file", return_value={
                "platform_id": "mihome",
                "path": str(self._devices_file("mihome")),
                "count": 1,
            }),
            patch.object(downloader, "refresh_platform_guides", return_value=[]),
        ):
            rc = cli.cmd_update(argparse.Namespace())

        self.assertEqual(rc, 0)
        joined = "\n".join(printed)
        self.assertIn("Platform catalog refresh failed: catalog endpoint down", joined)
        self.assertIn("Continuing with the local cached catalog.", joined)
        self.assertNotIn("Platform catalog refreshed.", joined)

    def test_setup_preserves_homeassistant_discovery_metadata(self):
        self._write_platform_devices("homeassistant", ["ha.xiaomi.switch.2wpro3"])
        connector = FakeConnector(
            poll_results=[],
            devices=[
                {
                    "did": "ha-device-1",
                    "name": "Xiaomi switch",
                    "model": "ha.xiaomi.switch.2wpro3",
                    "raw_model": "Xiaomi Smart Switch Pro 3",
                    "manufacturer": "Xiaomi",
                    "ha_device_id": "ha-device-1",
                    "primary_entity_id": "switch.xiaomi_2wpro3_middle",
                    "entity_ids": [
                        "switch.xiaomi_2wpro3_left",
                        "switch.xiaomi_2wpro3_middle",
                        "switch.xiaomi_2wpro3_right",
                    ],
                }
            ],
        )
        printed: list[str] = []

        with (
            patch.object(cli, "_refresh_catalog"),
            patch.object(cli, "_resolve_platform_or_exit", return_value="homeassistant"),
            patch.object(loader, "load_connector", return_value=connector),
            patch.object(downloader, "download_device", return_value="1.0.0"),
            patch.object(config, "set_device_version"),
            patch.object(cli, "_print", side_effect=printed.append),
        ):
            rc = cli.cmd_setup(
                argparse.Namespace(
                    platform="homeassistant",
                    did="ha-device-1",
                    device=None,
                    model="ha.xiaomi.switch.2wpro3",
                    version=None,
                    name="Main light switch",
                    location="Living room",
                    remark="Three-gang switch",
                )
            )

        self.assertEqual(rc, 0)
        records = store.load()
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["device_id"], "homeassistant:ha-device-1")
        self.assertEqual(record["entity_ids"], connector._devices[0]["entity_ids"])
        self.assertEqual(record["primary_entity_id"], "switch.xiaomi_2wpro3_middle")
        self.assertEqual(record["raw_model"], "Xiaomi Smart Switch Pro 3")
        self.assertEqual(record["manufacturer"], "Xiaomi")


if __name__ == "__main__":
    unittest.main()
