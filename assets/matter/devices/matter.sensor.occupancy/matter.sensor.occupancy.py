# -*- coding: utf-8 -*-
DEVICE_INFO = {
    "model": "matter.sensor.occupancy",
    "display_name": "Matter Occupancy Sensor",
    "manufacturer": "Matter",
    "category": "sensor",
    "platform": "matter",
}

SUPPORTED_ACTIONS = {
    "query_status",
}

ACTION_SPECS = []

STATUS_FIELDS = [
    {"field": "occupied", "description": "Whether occupancy is currently detected.", "type": "bool"},
    {"field": "available", "description": "Whether the Matter endpoint is currently reachable.", "type": "bool"},
]


class MatterOccupancySensor:
    def __init__(self, did: str, connector):
        self.did = did
        self.client = connector

    def _descriptor(self) -> dict:
        return self.client.get_device_descriptor(self.did)

    def query_status(self) -> str:
        info = self._descriptor()
        raw_value = self.client.read_device_attribute(self.did, self.client.OCCUPANCY_SENSING_CLUSTER_ID, 0)
        try:
            occupied = bool(int(raw_value or 0) & 0x01)
        except (TypeError, ValueError):
            occupied = False
        return f"occupied: {occupied}, available: {bool(info.get('available', False))}"

    def perform_action(self, action: str, **kwargs) -> str:
        del kwargs
        if action == "query_status":
            return self.query_status()
        return f"Error: unsupported action '{action}'."


DeviceClass = MatterOccupancySensor
