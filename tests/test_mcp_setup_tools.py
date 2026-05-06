# -*- coding: utf-8 -*-
import argparse
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import setup  # noqa: E402


class McpSetupToolsTests(unittest.TestCase):
    def setUp(self):
        setup._PENDING_PLATFORM_SELECTIONS.clear()
        setup._PENDING_DEVICE_SETUP_CONFIRMATIONS.clear()

    def tearDown(self):
        setup._PENDING_PLATFORM_SELECTIONS.clear()
        setup._PENDING_DEVICE_SETUP_CONFIRMATIONS.clear()

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

            def get_connect_qr(self, session_id):
                self.qr_session_id = session_id
                return b"png-bytes"

        connector = FakeConnector()
        with (
            patch.object(setup.cli, "_resolve_platform_or_exit", return_value="mihome"),
            patch.object(setup, "_prepare_platform_connector", return_value={"connector": {"status": "ready", "version": "1.0.6"}}),
            patch.object(setup.loader, "load_connector", return_value=connector),
            patch.object(setup, "_upload_temp_qr", return_value="https://api.entroflow.ai/v1/tmp/login-qr/token"),
        ):
            result = setup.platform_connect(
                "mihome",
                inputs={"room": "lab", "skip": None},
            )

        self.assertIn("status=pending", result)
        self.assertIn("session_id=session-1", result)
        self.assertIn("markdown_image=![EntroFlow platform login QR](https://api.entroflow.ai/v1/tmp/login-qr/token)", result)
        self.assertIn("public_url=https://api.entroflow.ai/v1/tmp/login-qr/token", result)
        self.assertIn("file_path=/shared/qr.png", result)
        self.assertIn("platform_connect_qr", result)
        self.assertIn("platform_connect_poll", result)
        self.assertEqual(connector.qr_session_id, "session-1")
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

    def test_platform_connect_qr_url_uploads_connector_bytes(self):
        class FakeConnector:
            def get_connect_qr(self, session_id):
                return b"png-bytes"

        with (
            patch.object(setup.cli, "_resolve_platform_or_exit", return_value="mihome"),
            patch.object(setup.loader, "load_connector", return_value=FakeConnector()),
            patch.object(setup, "_upload_temp_qr", return_value="https://api.entroflow.ai/v1/tmp/login-qr/token") as upload,
        ):
            result = setup.platform_connect_qr_url("mihome", "session-1")

        self.assertEqual(result, "https://api.entroflow.ai/v1/tmp/login-qr/token")
        upload.assert_called_once_with(b"png-bytes", 600)

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
            seen["supported_only"] = args.supported_only
            return 0

        with patch.object(setup.cli, "cmd_list_devices", fake_cmd):
            result = setup.platform_devices("")

        self.assertEqual(result, "OK")
        self.assertIsNone(seen["platform"])
        self.assertTrue(seen["supported_only"])

    def test_platform_devices_requires_platform_confirmation_for_specific_platform(self):
        result = setup.platform_devices("homeassistant")

        self.assertIn("requires platform confirmation", result)
        self.assertIn("Do not default to the previous platform", result)

    def test_platform_select_prepare_allows_specific_platform_devices(self):
        seen = {}

        def fake_cmd(args: argparse.Namespace) -> int:
            seen["platform"] = args.platform
            seen["supported_only"] = args.supported_only
            return 0

        with (
            patch.object(setup.cli, "_resolve_platform_or_exit", return_value="homeassistant"),
            patch.object(setup.config, "get_connected_iot_platforms", return_value=["homeassistant", "mihome"]),
        ):
            prepared = setup.platform_select_prepare("ha")
        token = re.search(r"platform_confirmation_token=(\S+)", prepared).group(1)

        with patch.object(setup.cli, "cmd_list_devices", fake_cmd):
            result = setup.platform_devices("homeassistant", platform_confirmation_token=token)

        self.assertEqual(result, "OK")
        self.assertEqual(seen["platform"], "homeassistant")
        self.assertTrue(seen["supported_only"])

    def test_device_setup_requires_confirmation(self):
        result = setup.device_setup(
            platform="mihome",
            did="1",
            model="zhimi.airpurifier.test",
            name="Air Purifier",
            location="Living Room",
            remark="main purifier",
        )

        self.assertIn("requires a valid confirmation_token", result)

    def test_device_setup_prepare_returns_confirmation_token(self):
        result = setup.device_setup_prepare(
            platform="mihome",
            did="1",
            model="zhimi.airpurifier.test",
            name="Air Purifier",
            location="Living Room",
            remark="main purifier",
        )

        self.assertIn("Device setup confirmation required", result)
        self.assertIn("platform=mihome", result)
        self.assertIn("did=1", result)
        self.assertRegex(result, r"confirmation_token=\S+")

    def test_device_setup_rejects_token_for_changed_fields(self):
        prepared = setup.device_setup_prepare(
            platform="mihome",
            did="1",
            model="zhimi.airpurifier.test",
            name="Air Purifier",
            location="Living Room",
            remark="main purifier",
        )
        token = re.search(r"confirmation_token=(\S+)", prepared).group(1)

        result = setup.device_setup(
            platform="mihome",
            did="1",
            model="zhimi.airpurifier.test",
            name="Different Name",
            location="Living Room",
            remark="main purifier",
            confirmation_token=token,
        )

        self.assertIn("does not match", result)

    def test_device_setup_passes_required_registration_fields(self):
        seen = {}

        def fake_cmd(args: argparse.Namespace) -> int:
            seen.update(vars(args))
            print("Registered device: Air Purifier (mihome:1)")
            return 0

        prepared = setup.device_setup_prepare(
            platform="mihome",
            did="1",
            model="zhimi.airpurifier.test",
            version="1.0.0",
            name="Air Purifier",
            location="Living Room",
            remark="main purifier",
        )
        token = re.search(r"confirmation_token=(\S+)", prepared).group(1)

        with patch.object(setup.cli, "cmd_setup", fake_cmd):
            result = setup.device_setup(
                platform="mihome",
                did="1",
                model="zhimi.airpurifier.test",
                version="1.0.0",
                name="Air Purifier",
                location="Living Room",
                remark="main purifier",
                confirmed=True,
                confirmation_token=token,
            )

        self.assertIn("Registered device", result)
        self.assertIsNone(seen["device"])
        self.assertEqual(seen["platform"], "mihome")
        self.assertEqual(seen["did"], "1")
        self.assertEqual(seen["model"], "zhimi.airpurifier.test")
        self.assertEqual(seen["version"], "1.0.0")
        self.assertEqual(seen["name"], "Air Purifier")
        self.assertTrue(seen["confirmed"])

    def test_run_cli_reports_nonzero_status(self):
        def fake_cmd(_: argparse.Namespace) -> int:
            print("not connected")
            return 2

        result = setup._run_cli(fake_cmd, argparse.Namespace())

        self.assertIn("not connected", result)
        self.assertIn("Command exited with status 2.", result)


if __name__ == "__main__":
    unittest.main()
