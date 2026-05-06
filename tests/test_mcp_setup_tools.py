# -*- coding: utf-8 -*-
import argparse
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import setup  # noqa: E402


class McpSetupToolsTests(unittest.TestCase):
    def test_platform_list_wraps_cli_output(self):
        seen = {}

        def fake_cmd(args: argparse.Namespace) -> int:
            seen["query"] = args.query
            print("Found 1 supported platform(s):")
            print("- mihome (Xiaomi IoT)")
            return 0

        with patch.object(setup.cli, "cmd_list_platforms", fake_cmd):
            result = setup.platform_list("mi")

        self.assertEqual(seen["query"], "mi")
        self.assertIn("mihome", result)

    def test_platform_connect_starts_flow_without_polling(self):
        class FakeConnector:
            def connect(self, context):
                self.context = context
                return {
                    "status": "pending",
                    "session_id": "session-1",
                    "expires_in": 600,
                    "message": "Scan QR",
                    "actions": [{"type": "scan_qr", "file_path": "/shared/qr.png"}],
                }

        connector = FakeConnector()
        with (
            patch.object(setup.cli, "_resolve_platform_or_exit", return_value="mihome"),
            patch.object(setup, "_prepare_platform_connector", return_value={"connector": {"status": "ready", "version": "1.0.6"}}),
            patch.object(setup.loader, "load_connector", return_value=connector),
        ):
            result = setup.platform_connect(
                "mihome",
                inputs={"room": "lab", "skip": None},
            )

        self.assertIn("status=pending", result)
        self.assertIn("session_id=session-1", result)
        self.assertIn("file_path=/shared/qr.png", result)
        self.assertIn("platform_connect_qr", result)
        self.assertIn("platform_connect_poll", result)
        self.assertEqual(connector.context["presentation"], "file")
        self.assertEqual(connector.context["inputs"], {"room": "lab"})

    def test_platform_connect_qr_returns_connector_bytes(self):
        class FakeConnector:
            def get_connect_qr(self, session_id):
                self.session_id = session_id
                return b"png-bytes"

        connector = FakeConnector()
        with (
            patch.object(setup.cli, "_resolve_platform_or_exit", return_value="mihome"),
            patch.object(setup.loader, "load_connector", return_value=connector),
        ):
            result = setup.platform_connect_qr("mihome", "session-1")

        self.assertEqual(result, b"png-bytes")
        self.assertEqual(connector.session_id, "session-1")

    def test_platform_connect_qr_reads_connector_file(self):
        qr_path = ROOT / "tests" / "tmp-qr.png"
        qr_path.write_bytes(b"file-png")
        self.addCleanup(lambda: qr_path.exists() and qr_path.unlink())

        class FakeConnector:
            def get_connect_qr(self, session_id):
                return {"file_path": str(qr_path)}

        with (
            patch.object(setup.cli, "_resolve_platform_or_exit", return_value="mihome"),
            patch.object(setup.loader, "load_connector", return_value=FakeConnector()),
        ):
            result = setup.platform_connect_qr("mihome", "session-1")

        self.assertEqual(result, b"file-png")

    def test_platform_connect_defaults_to_file_presentation_for_remote_agents(self):
        class FakeConnector:
            def connect(self, context):
                self.context = context
                return {"status": "connected", "message": "connected"}

        connector = FakeConnector()
        with (
            patch.object(setup.cli, "_resolve_platform_or_exit", return_value="mihome"),
            patch.object(setup, "_prepare_platform_connector", return_value={}),
            patch.object(setup.loader, "load_connector", return_value=connector),
            patch.object(setup.config, "add_connected_iot_platform"),
        ):
            result = setup.platform_connect("mihome")

        self.assertIn("status=connected", result)
        self.assertEqual(connector.context["presentation"], "file")

    def test_platform_connect_poll_marks_connected(self):
        class FakeConnector:
            def poll_connect(self, session_id, context):
                self.session_id = session_id
                self.context = context
                return {"status": "connected", "message": "done"}

        connector = FakeConnector()
        with (
            patch.object(setup.cli, "_resolve_platform_or_exit", return_value="mihome"),
            patch.object(setup.loader, "load_connector", return_value=connector),
            patch.object(setup.config, "add_connected_iot_platform") as add_connected,
        ):
            result = setup.platform_connect_poll("mihome", "session-1")

        self.assertIn("status=connected", result)
        self.assertEqual(connector.session_id, "session-1")
        add_connected.assert_called_once_with("mihome")

    def test_prepare_platform_connector_clears_connector_cache_after_update(self):
        with (
            patch.object(setup.cli.downloader, "download_platform_guide", return_value=None),
            patch.object(setup.cli, "_ensure_platform_connector_ready", return_value={"status": "updated", "version": "1.0.7"}),
            patch.object(setup.cli, "_refresh_platform_devices_table", return_value=None),
            patch.object(setup.loader, "clear_connector_cache") as clear_cache,
        ):
            report = setup._prepare_platform_connector("mihome")

        self.assertEqual(report["connector"]["version"], "1.0.7")
        clear_cache.assert_called_once_with("mihome")

    def test_platform_devices_maps_empty_platform_to_none(self):
        seen = {}

        def fake_cmd(args: argparse.Namespace) -> int:
            seen["platform"] = args.platform
            return 0

        with patch.object(setup.cli, "cmd_list_devices", fake_cmd):
            result = setup.platform_devices("")

        self.assertEqual(result, "OK")
        self.assertIsNone(seen["platform"])

    def test_device_setup_passes_required_registration_fields(self):
        seen = {}

        def fake_cmd(args: argparse.Namespace) -> int:
            seen.update(vars(args))
            print("Registered device: Air Purifier (mihome:1)")
            return 0

        with patch.object(setup.cli, "cmd_setup", fake_cmd):
            result = setup.device_setup(
                platform="mihome",
                did="1",
                model="zhimi.airpurifier.test",
                version="1.0.0",
                name="Air Purifier",
                location="Living Room",
                remark="main purifier",
            )

        self.assertIn("Registered device", result)
        self.assertIsNone(seen["device"])
        self.assertEqual(seen["platform"], "mihome")
        self.assertEqual(seen["did"], "1")
        self.assertEqual(seen["model"], "zhimi.airpurifier.test")
        self.assertEqual(seen["version"], "1.0.0")
        self.assertEqual(seen["name"], "Air Purifier")

    def test_run_cli_reports_nonzero_status(self):
        def fake_cmd(_: argparse.Namespace) -> int:
            print("not connected")
            return 2

        result = setup._run_cli(fake_cmd, argparse.Namespace())

        self.assertIn("not connected", result)
        self.assertIn("Command exited with status 2.", result)


if __name__ == "__main__":
    unittest.main()
