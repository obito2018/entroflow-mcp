# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import device as device_tools  # noqa: E402


class FakeDevice:
    def __init__(self):
        self.calls = []

    def perform_action(self, action_name, **kwargs):
        self.calls.append((action_name, kwargs))
        return "OK"


class DeviceControlTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "device_id": "homeassistant:switch.xiaomi_2wpro3_de32",
            "name": "Main light switch",
            "platform": "homeassistant",
            "model": "ha.xiaomi.switch.2wpro3",
        }

    def test_action_object_forwards_args_to_driver(self):
        fake = FakeDevice()

        with patch.object(device_tools.store, "find", return_value=self.record), patch.object(
            device_tools.loader, "create_device_instance", return_value=fake
        ):
            result = device_tools.device_control(
                self.record["device_id"],
                {"action": "turn_on", "args": {"channels": "middle"}},
            )

        self.assertIn("turn_on: OK", result)
        self.assertEqual(fake.calls, [("turn_on", {"channels": "middle"})])

    def test_top_level_action_args_are_rejected_with_guidance(self):
        fake = FakeDevice()

        with patch.object(device_tools.store, "find", return_value=self.record), patch.object(
            device_tools.loader, "create_device_instance", return_value=fake
        ):
            result = device_tools.device_control(
                self.record["device_id"],
                {"action": "turn_on", "channels": "middle"},
            )

        self.assertIn("must be nested under args", result)
        self.assertIn("{'action': '<supported_action>', 'args': {'channels': 'middle'}}", result)
        self.assertEqual(fake.calls, [])

    def test_json_string_action_payload_is_decoded(self):
        fake = FakeDevice()

        with patch.object(device_tools.store, "find", return_value=self.record), patch.object(
            device_tools.loader, "create_device_instance", return_value=fake
        ):
            result = device_tools.device_control(
                self.record["device_id"],
                '{"action": "set_preset_mode", "args": {"preset_mode": "Auto"}}',
            )

        self.assertIn("set_preset_mode: OK", result)
        self.assertEqual(fake.calls, [("set_preset_mode", {"preset_mode": "Auto"})])

    def test_json_string_args_payload_is_decoded(self):
        fake = FakeDevice()

        with patch.object(device_tools.store, "find", return_value=self.record), patch.object(
            device_tools.loader, "create_device_instance", return_value=fake
        ):
            result = device_tools.device_control(
                self.record["device_id"],
                {"action": "set_preset_mode", "args": '{"preset_mode": "Auto"}'},
            )

        self.assertIn("set_preset_mode: OK", result)
        self.assertEqual(fake.calls, [("set_preset_mode", {"preset_mode": "Auto"})])


if __name__ == "__main__":
    unittest.main()
