# -*- coding: utf-8 -*-
from typing import Any


DEVICE_INFO = {
    "model": "matter.lock",
    "display_name": "Matter Door Lock",
    "manufacturer": "Matter",
    "category": "lock",
    "platform": "matter",
}

SUPPORTED_ACTIONS = {
    "lock",
    "unlock",
    "query_status",
}

ACTION_SPECS = [
    {"action": "lock", "description": "Lock the Matter door lock.", "args": "None", "range": "-"},
    {"action": "unlock", "description": "Unlock the Matter door lock.", "args": "None", "range": "-"},
]

STATUS_FIELDS = [
    {"field": "lock_state", "description": "Current lock state.", "type": "string"},
    {"field": "actuator_enabled", "description": "Whether the lock actuator is enabled.", "type": "bool or null"},
    {"field": "available", "description": "Whether the Matter endpoint is currently reachable.", "type": "bool"},
]


LOCK_STATE_MAP = {
    0: "not_fully_locked",
    1: "locked",
    2: "unlocked",
    3: "unlatched",
}


class MatterDoorLock:
    def __init__(self, did: str, connector):
        self.did = did
        self.client = connector

    def _descriptor(self) -> dict:
        return self.client.get_device_descriptor(self.did)

    def query_status(self) -> str:
        info = self._descriptor()
        lock_state_raw = self.client.read_device_attribute(self.did, self.client.DOOR_LOCK_CLUSTER_ID, 0)
        actuator_enabled = self.client.read_device_attribute(self.did, self.client.DOOR_LOCK_CLUSTER_ID, 2)
        lock_state = LOCK_STATE_MAP.get(lock_state_raw, f"unknown({lock_state_raw})")
        return (
            f"lock_state: {lock_state}, "
            f"actuator_enabled: {actuator_enabled}, "
            f"available: {bool(info.get('available', False))}"
        )

    def lock(self) -> str:
        self.client.invoke_device_command(
            self.did,
            self.client.DOOR_LOCK_CLUSTER_ID,
            "LockDoor",
            payload={},
            timed_request_timeout_ms=1000,
        )
        return "lock sent."

    def unlock(self) -> str:
        self.client.invoke_device_command(
            self.did,
            self.client.DOOR_LOCK_CLUSTER_ID,
            "UnlockDoor",
            payload={},
            timed_request_timeout_ms=1000,
        )
        return "unlock sent."

    def perform_action(self, action: str, **kwargs) -> str:
        del kwargs
        if action == "lock":
            return self.lock()
        if action == "unlock":
            return self.unlock()
        if action == "query_status":
            return self.query_status()
        return f"Error: unsupported action '{action}'."


DeviceClass = MatterDoorLock
