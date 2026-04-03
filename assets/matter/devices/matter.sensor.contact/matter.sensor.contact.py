# -*- coding: utf-8 -*-
DEVICE_INFO = {
    "model": "matter.sensor.contact",
    "display_name": "Matter Contact Sensor",
    "manufacturer": "Matter",
    "category": "sensor",
    "platform": "matter",
}

SUPPORTED_ACTIONS = {
    "query_status",
}

ACTION_SPECS = []

STATUS_FIELDS = [
    {"field": "contact_detected", "description": "Whether contact is currently detected.", "type": "bool"},
    {"field": "state", "description": "Human-friendly state derived from contact detection.", "type": "string"},
    {"field": "available", "description": "Whether the Matter endpoint is currently reachable.", "type": "bool"},
]


class MatterContactSensor:
    def __init__(self, did: str, connector):
        self.did = did
        self.client = connector

    def _descriptor(self) -> dict:
        return self.client.get_device_descriptor(self.did)

    def query_status(self) -> str:
        info = self._descriptor()
        raw_value = self.client.read_device_attribute(self.did, self.client.BOOLEAN_STATE_CLUSTER_ID, 0)
        contact_detected = bool(raw_value)
        state = "closed" if contact_detected else "open"
        return (
            f"contact_detected: {contact_detected}, "
            f"state: {state}, "
            f"available: {bool(info.get('available', False))}"
        )

    def perform_action(self, action: str, **kwargs) -> str:
        del kwargs
        if action == "query_status":
            return self.query_status()
        return f"Error: unsupported action '{action}'."


DeviceClass = MatterContactSensor
