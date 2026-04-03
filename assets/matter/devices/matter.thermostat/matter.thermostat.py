# -*- coding: utf-8 -*-
from typing import Any


DEVICE_INFO = {
    "model": "matter.thermostat",
    "display_name": "Matter Thermostat",
    "manufacturer": "Matter",
    "category": "climate",
    "platform": "matter",
}

SUPPORTED_ACTIONS = {
    "set_mode",
    "set_heating_setpoint",
    "set_cooling_setpoint",
    "query_status",
}

ACTION_SPECS = [
    {"action": "set_mode", "description": "Set the thermostat mode.", "args": "mode", "range": "off/auto/cool/heat"},
    {"action": "set_heating_setpoint", "description": "Set occupied heating setpoint in Celsius.", "args": "celsius", "range": "5~35"},
    {"action": "set_cooling_setpoint", "description": "Set occupied cooling setpoint in Celsius.", "args": "celsius", "range": "5~35"},
]

STATUS_FIELDS = [
    {"field": "mode", "description": "Current thermostat mode.", "type": "string"},
    {"field": "local_temperature_c", "description": "Current local temperature in Celsius.", "type": "float or null"},
    {"field": "heating_setpoint_c", "description": "Current occupied heating setpoint in Celsius.", "type": "float or null"},
    {"field": "cooling_setpoint_c", "description": "Current occupied cooling setpoint in Celsius.", "type": "float or null"},
    {"field": "available", "description": "Whether the Matter endpoint is currently reachable.", "type": "bool"},
]


SYSTEM_MODE_MAP = {
    0: "off",
    1: "auto",
    3: "cool",
    4: "heat",
}

SYSTEM_MODE_VALUES = {value: key for key, value in SYSTEM_MODE_MAP.items()}


def _from_centidegrees(value: Any) -> Any:
    if value is None:
        return None
    try:
        return round(float(value) / 100.0, 1)
    except (TypeError, ValueError):
        return None


def _to_centidegrees(value: float) -> int:
    return int(round(value * 100))


class MatterThermostat:
    def __init__(self, did: str, connector):
        self.did = did
        self.client = connector

    def _descriptor(self) -> dict:
        return self.client.get_device_descriptor(self.did)

    def query_status(self) -> str:
        info = self._descriptor()
        mode_raw = self.client.read_device_attribute(self.did, self.client.THERMOSTAT_CLUSTER_ID, 0x001C)
        local_temp = _from_centidegrees(self.client.read_device_attribute(self.did, self.client.THERMOSTAT_CLUSTER_ID, 0x0000))
        heat_setpoint = _from_centidegrees(self.client.read_device_attribute(self.did, self.client.THERMOSTAT_CLUSTER_ID, 0x0012))
        cool_setpoint = _from_centidegrees(self.client.read_device_attribute(self.did, self.client.THERMOSTAT_CLUSTER_ID, 0x0011))
        mode = SYSTEM_MODE_MAP.get(mode_raw, f"unknown({mode_raw})")
        return (
            f"mode: {mode}, "
            f"local_temperature_c: {local_temp}, "
            f"heating_setpoint_c: {heat_setpoint}, "
            f"cooling_setpoint_c: {cool_setpoint}, "
            f"available: {bool(info.get('available', False))}"
        )

    def set_mode(self, mode: Any) -> str:
        normalized = str(mode or "").strip().lower()
        if normalized not in SYSTEM_MODE_VALUES:
            return "Error: mode must be one of off, auto, cool, or heat."
        self.client.write_device_attribute(
            self.did,
            self.client.THERMOSTAT_CLUSTER_ID,
            0x001C,
            SYSTEM_MODE_VALUES[normalized],
        )
        return f"mode set to {normalized}."

    def set_heating_setpoint(self, celsius: Any) -> str:
        try:
            target = float(celsius)
        except (TypeError, ValueError):
            return "Error: celsius must be a number between 5 and 35."
        if not 5.0 <= target <= 35.0:
            return "Error: celsius must be between 5 and 35."
        self.client.write_device_attribute(
            self.did,
            self.client.THERMOSTAT_CLUSTER_ID,
            0x0012,
            _to_centidegrees(target),
        )
        return f"heating setpoint set to {target:.1f}C."

    def set_cooling_setpoint(self, celsius: Any) -> str:
        try:
            target = float(celsius)
        except (TypeError, ValueError):
            return "Error: celsius must be a number between 5 and 35."
        if not 5.0 <= target <= 35.0:
            return "Error: celsius must be between 5 and 35."
        self.client.write_device_attribute(
            self.did,
            self.client.THERMOSTAT_CLUSTER_ID,
            0x0011,
            _to_centidegrees(target),
        )
        return f"cooling setpoint set to {target:.1f}C."

    def perform_action(self, action: str, **kwargs) -> str:
        if action == "set_mode":
            return self.set_mode(kwargs.get("mode"))
        if action == "set_heating_setpoint":
            return self.set_heating_setpoint(kwargs.get("celsius"))
        if action == "set_cooling_setpoint":
            return self.set_cooling_setpoint(kwargs.get("celsius"))
        if action == "query_status":
            return self.query_status()
        return f"Error: unsupported action '{action}'."


DeviceClass = MatterThermostat
