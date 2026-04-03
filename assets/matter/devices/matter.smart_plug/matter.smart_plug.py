# -*- coding: utf-8 -*-
from typing import Any


DEVICE_INFO = {
    "model": "matter.smart_plug",
    "display_name": "Matter Smart Plug",
    "manufacturer": "Matter",
    "category": "switch",
    "platform": "matter",
}

SUPPORTED_ACTIONS = {
    "turn_on",
    "turn_off",
    "toggle",
    "query_status",
}

ACTION_SPECS = [
    {"action": "turn_on", "description": "Turn the Matter smart plug on.", "args": "None", "range": "-"},
    {"action": "turn_off", "description": "Turn the Matter smart plug off.", "args": "None", "range": "-"},
    {"action": "toggle", "description": "Toggle the Matter smart plug state.", "args": "None", "range": "-"},
]

STATUS_FIELDS = [
    {"field": "power", "description": "Current outlet power state.", "type": "string"},
    {"field": "available", "description": "Whether the Matter endpoint is currently reachable.", "type": "bool"},
]


class MatterSmartPlug:
    def __init__(self, did: str, connector):
        self.did = did
        self.client = connector

    def _descriptor(self) -> dict:
        return self.client.get_device_descriptor(self.did)

    def query_status(self) -> str:
        info = self._descriptor()
        power = "on" if bool(self.client.read_device_attribute(self.did, self.client.ON_OFF_CLUSTER_ID, 0)) else "off"
        return f"power: {power}, available: {bool(info.get('available', False))}"

    def turn_on(self) -> str:
        self.client.invoke_device_command(self.did, self.client.ON_OFF_CLUSTER_ID, "On")
        return "turn_on sent."

    def turn_off(self) -> str:
        self.client.invoke_device_command(self.did, self.client.ON_OFF_CLUSTER_ID, "Off")
        return "turn_off sent."

    def toggle(self) -> str:
        self.client.invoke_device_command(self.did, self.client.ON_OFF_CLUSTER_ID, "Toggle")
        return "toggle sent."

    def perform_action(self, action: str, **kwargs) -> str:
        del kwargs
        if action == "turn_on":
            return self.turn_on()
        if action == "turn_off":
            return self.turn_off()
        if action == "toggle":
            return self.toggle()
        if action == "query_status":
            return self.query_status()
        return f"Error: unsupported action '{action}'."


DeviceClass = MatterSmartPlug
