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
from core import config, downloader, loader  # noqa: E402
from tools import system as system_tools  # noqa: E402


class NonInteractiveStdin:
    def isatty(self) -> bool:
        return False


class FakeConnector:
    def __init__(
        self,
        poll_results: list[dict],
        devices: list[dict] | None = None,
        qr_file_path: str | None = None,
    ):
        self._poll_results = list(poll_results)
        self._devices = devices or []
        self._qr_file_path = qr_file_path
        self.poll_calls = 0

    def start_qr_login(self, region: str = "cn", login_option: str = "local-page") -> dict:
        payload = {
            "session_id": "session-1",
            "qr_url": "https://example.com/login",
            "expires_in": 120,
            "type": "qrcode",
            "login_option": login_option,
        }
        if login_option == "qr-file" and self._qr_file_path:
            payload["qr_file_path"] = self._qr_file_path
        return payload

    def poll_qr_login(self, session_id: str) -> dict:
        result = self._poll_results[min(self.poll_calls, len(self._poll_results) - 1)]
        self.poll_calls += 1
        return result

    def list_devices(self) -> list[dict]:
        return list(self._devices)


class MihomeCliFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.home = Path(self.temp_dir.name) / ".entroflow"
        self.assets_dir = self.home / "assets"
        self.docs_dir = self.home / "docs" / "platforms"
        self.runtime_dir = self.home / "runtime"
        self.config_path = self.home / "config.json"
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
            rc = cli.cmd_connect(argparse.Namespace(platform="mihome", no_prompt=False, login_option="local-page"))

        self.assertEqual(rc, 0)
        self.assertEqual(connector.poll_calls, 2)
        self.assertIn("Non-interactive mode detected; waiting for login confirmation...", printed)

    def test_connect_mihome_qr_file_mode_prints_local_file_and_skips_browser(self):
        self._write_platform_devices("mihome", ["old.model"])
        qr_file = str(self.runtime_dir / "mihome-login-session-1.png")
        connector = FakeConnector(
            poll_results=[
                {"status": "waiting", "message": "Waiting for confirmation..."},
                {"status": "ok"},
            ],
            qr_file_path=qr_file,
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
            rc = cli.cmd_connect(argparse.Namespace(platform="mihome", no_prompt=False, login_option="qr-file"))

        self.assertEqual(rc, 0)
        joined = "\n".join(printed)
        self.assertIn("Login QR code was generated as a local file.", joined)
        self.assertIn(qr_file, joined)
        self.assertIn("https://example.com/login", joined)

    def test_connect_falls_back_for_legacy_connector_without_login_option_argument(self):
        self._write_platform_devices("mihome", ["old.model"])
        printed: list[str] = []

        class LegacyConnector:
            def __init__(self):
                self.poll_calls = 0

            def start_qr_login(self, region: str = "cn") -> dict:
                return {
                    "session_id": "legacy-session",
                    "qr_url": "https://example.com/legacy-login",
                    "expires_in": 120,
                    "type": "qrcode",
                }

            def poll_qr_login(self, session_id: str) -> dict:
                self.poll_calls += 1
                return {"status": "ok"}

        connector = LegacyConnector()

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
        ):
            rc = cli.cmd_connect(argparse.Namespace(platform="mihome", no_prompt=False, login_option="local-page"))

        self.assertEqual(rc, 0)
        self.assertEqual(connector.poll_calls, 1)
        self.assertIn("https://example.com/legacy-login", "\n".join(printed))

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
            rc = cli.cmd_connect(argparse.Namespace(platform="mihome", no_prompt=False, login_option="local-page"))

        self.assertEqual(rc, 0)
        self.assertEqual(config.get_platform_version("mihome"), "1.0.4")
        self.assertIn("Updated platform connector mihome (1.0.3 -> v1.0.4)", "\n".join(printed))

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


if __name__ == "__main__":
    unittest.main()
