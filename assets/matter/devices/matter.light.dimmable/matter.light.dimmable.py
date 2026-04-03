# -*- coding: utf-8 -*-
from typing import Any


DEVICE_INFO = {
    "model": "matter.light.dimmable",
    "display_name": "Matter Dimmable Light",
    "manufacturer": "Matter",
    "category": "light",
    "platform": "matter",
}

SUPPORTED_ACTIONS = {
    "turn_on",
    "turn_off",
    "toggle",
    "set_brightness",
    "query_status",
}

ACTION_SPECS = [
    {"action": "turn_on", "description": "Turn the Matter light on.", "args": "None", "range": "-"},
    {"action": "turn_off", "description": "Turn the Matter light off.", "args": "None", "range": "-"},
    {"action": "toggle", "description": "Toggle the Matter light state.", "args": "None", "range": "-"},
    {"action": "set_brightness", "description": "Set brightness as a percentage.", "args": "value", "range": "1~100"},
]

STATUS_FIELDS = [
    {"field": "power", "description": "Current light power state.", "type": "string"},
    {"field": "brightness_pct", "description": "Current brightness percentage.", "type": "int or null"},
    {"field": "available", "description": "Whether the Matter endpoint is currently reachable.", "type": "bool"},
]


def _pct_to_level(value: int) -> int:
    return max(1, min(254, round((value / 100.0) * 254)))


def _level_to_pct(value: Any) -> Any:
    if value is None:
        return None
    try:
        return max(0, min(100, round((float(value) / 254.0) * 100)))
    except (TypeError, ValueError):
        return None


class MatterDimmableLight:
    def __init__(self, did: str, connector):
        self.did = did
        self.client = connector

    def _descriptor(self) -> dict:
        return self.client.get_device_descriptor(self.did)

    def query_status(self) -> str:
        info = self._descriptor()
        power = "on" if bool(self.client.read_device_attribute(self.did, self.client.ON_OFF_CLUSTER_ID, 0)) else "off"
        brightness_pct = _level_to_pct(self.client.read_device_attribute(self.did, self.client.LEVEL_CONTROL_CLUSTER_ID, 0))
        return (
            f"power: {power}, "
            f"brightness_pct: {brightness_pct}, "
            f"available: {bool(info.get('available', False))}"
        )

    def turn_on(self) -> str:
        self.client.invoke_device_command(self.did, self.client.ON_OFF_CLUSTER_ID, "On")
        return "turn_on sent."

    def turn_off(self) -> str:
        self.client.invoke_device_command(self.did, self.client.ON_OFF_CLUSTER_ID, "Off")
        return "turn_off sent."

    def toggle(self) -> str:
        self.client.invoke_device_command(self.did, self.client.ON_OFF_CLUSTER_ID, "Toggle")
        return "toggle sent."

    def set_brightness(self, value: Any) -> str:
        try:
            brightness_pct = int(value)
        except (TypeError, ValueError):
            return "Error: value must be an integer between 1 and 100."
        if not 1 <= brightness_pct <= 100:
            return "Error: value must be between 1 and 100."

        self.client.invoke_device_command(
            self.did,
            self.client.LEVEL_CONTROL_CLUSTER_ID,
            "MoveToLevelWithOnOff",
            payload={
                "level": _pct_to_level(brightness_pct),
                "transitionTime": 0,
                "optionsMask": 0,
                "optionsOverride": 0,
            },
        )
        return f"brightness set to {brightness_pct}%."

    def perform_action(self, action: str, **kwargs) -> str:
        if action == "turn_on":
            return self.turn_on()
        if action == "turn_off":
            return self.turn_off()
        if action == "toggle":
            return self.toggle()
        if action == "set_brightness":
            return self.set_brightness(kwargs.get("value"))
        if action == "query_status":
            return self.query_status()
        return f"Error: unsupported action '{action}'."


DeviceClass = MatterDimmableLight
