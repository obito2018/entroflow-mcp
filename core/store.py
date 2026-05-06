# -*- coding: utf-8 -*-
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

STORE_PATH = Path.home() / ".entroflow" / "data" / "devices.json"


def load() -> List[Dict[str, Any]]:
    if not STORE_PATH.exists():
        return []
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save(devices: List[Dict[str, Any]]):
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORE_PATH.write_text(
        json.dumps(devices, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def find(device_id: str) -> Optional[Dict[str, Any]]:
    for d in load():
        if d.get("device_id") == device_id:
            return d
    return None


def _clean_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}

    ignored = {"did", "model", "platform", "name", "device_id", "created_at"}
    result: Dict[str, Any] = {}
    for key, value in metadata.items():
        if key in ignored or value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            result[key] = value
        elif isinstance(value, list):
            cleaned = [item for item in value if isinstance(item, (str, int, float, bool, dict))]
            if cleaned:
                result[key] = cleaned
        elif isinstance(value, dict):
            if value:
                result[key] = value
    return result


def register(
    did: str,
    model: str,
    platform: str,
    name: str,
    location: str,
    remark: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    device_id = f"{platform}:{did}"
    devices = load()
    for d in devices:
        if d.get("device_id") == device_id:
            return {"ok": False, "message": f"设备 '{device_id}' 已注册为 '{d.get('name')}'。"}
    record = {
        "device_id": device_id,
        "did": did,
        "model": model,
        "platform": platform,
        "name": name,
        "location": location,
        "remark": remark,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    record.update(_clean_metadata(metadata))
    devices.append(record)
    save(devices)
    return {"ok": True, "record": record}
