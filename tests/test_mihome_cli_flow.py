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
    def __init__(self, poll_results: list[dict], devices: list[dict] | None = None):
        self._poll_results = list(poll_results)
        self._devices = devices or []
        self.poll_calls = 0

    def start_qr_login(self, region: str = "cn") -> dict:
        return {
            "session_id": "session-1",
            "qr_url": "https://example.com/login",
            "expires_in": 120,
            "type": "qrcode",
        }

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

        self.patches = [
            patch.object(cli, "ASSETS_DIR", self.assets_dir),
            patch.object(cli, "PLATFORM_DOCS_DIR", self.docs_dir),
            patch.object(config, "CONFIG_PATH", self.config_path),
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
            rc = cli.cmd_connect(argparse.Namespace(platform="mihome", no_prompt=False))

        self.assertEqual(rc, 0)
        self.assertEqual(connector.poll_calls, 2)
        self.assertIn("Non-interactive mode detected; waiting for login confirmation...", printed)

    def test_update_refreshes_platform_device_table_even_without_platform_version_change(self):
        config.set_platform_version("mihome", "1.0.3")
        config.add_installed_platform("mihome")
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


if __name__ == "__main__":
    unittest.main()
