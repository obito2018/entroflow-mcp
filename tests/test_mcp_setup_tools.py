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

    def test_platform_connect_passes_non_interactive_connector_inputs(self):
        seen = {}

        def fake_cmd(args: argparse.Namespace) -> int:
            seen.update(vars(args))
            print("connected")
            return 0

        with patch.object(setup.cli, "cmd_connect", fake_cmd):
            result = setup.platform_connect(
                "homeassistant",
                url="http://ha.local:8123",
                token="secret-token",
                inputs={"room": "lab", "skip": None},
                presentation="none",
                timeout=30,
            )

        self.assertEqual(result, "connected")
        self.assertEqual(seen["platform"], "homeassistant")
        self.assertTrue(seen["no_prompt"])
        self.assertEqual(seen["url"], "http://ha.local:8123")
        self.assertEqual(seen["token"], "secret-token")
        self.assertEqual(seen["input"], ["room=lab"])
        self.assertEqual(seen["presentation"], "none")
        self.assertEqual(seen["timeout"], 30)

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
