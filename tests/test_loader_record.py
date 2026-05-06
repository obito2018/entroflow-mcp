# -*- coding: utf-8 -*-
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import loader  # noqa: E402


class RecordAwareDevice:
    def __init__(self, did, connector, record):
        self.did = did
        self.connector = connector
        self.record = record


class LegacyDevice:
    def __init__(self, did, connector):
        self.did = did
        self.connector = connector


class LoaderRecordTests(unittest.TestCase):
    def test_create_device_instance_passes_record_when_driver_accepts_it(self):
        record = {"platform": "homeassistant", "model": "ha.test", "did": "dev-1", "entity_ids": ["light.a"]}
        module = type("Module", (), {"DeviceClass": RecordAwareDevice})
        connector = object()

        with patch.object(loader, "load_connector", return_value=connector), patch.object(
            loader, "load_device_class", return_value=module
        ):
            device = loader.create_device_instance(record)

        self.assertIs(device.record, record)
        self.assertEqual(device.did, "dev-1")
        self.assertIs(device.connector, connector)

    def test_create_device_instance_falls_back_for_legacy_driver(self):
        record = {"platform": "mihome", "model": "legacy.test", "did": "dev-2"}
        module = type("Module", (), {"DeviceClass": LegacyDevice})
        connector = object()

        with patch.object(loader, "load_connector", return_value=connector), patch.object(
            loader, "load_device_class", return_value=module
        ):
            device = loader.create_device_instance(record)

        self.assertEqual(device.did, "dev-2")
        self.assertIs(device.connector, connector)


if __name__ == "__main__":
    unittest.main()
