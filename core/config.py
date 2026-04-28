# -*- coding: utf-8 -*-
import json
import uuid
from pathlib import Path
from typing import Any, Dict

CONFIG_PATH = Path.home() / ".entroflow" / "config.json"
ASSETS_DIR = Path.home() / ".entroflow" / "assets"


def _load() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save(data: Dict[str, Any]):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_install_id() -> str:
    data = _load()
    if "install_id" not in data:
        data["install_id"] = str(uuid.uuid4())
        _save(data)
    return data["install_id"]


def _asset_record(data: Dict[str, Any], platform: str) -> Dict[str, Any]:
    return data.setdefault("assets", {}).setdefault(platform, {})


def get_platform_version(platform: str) -> str | None:
    return _load().get("assets", {}).get(platform, {}).get("version")


def set_platform_version(platform: str, version: str):
    data = _load()
    record = _asset_record(data, platform)
    record["version"] = version
    _save(data)


def get_device_version(platform: str, model: str) -> str | None:
    return _load().get("assets", {}).get(platform, {}).get("devices", {}).get(model)


def set_device_version(platform: str, model: str, version: str):
    data = _load()
    record = _asset_record(data, platform)
    record.setdefault("devices", {})[model] = version
    _save(data)


def get_asset_version(asset_type: str, name: str) -> str | None:
    if asset_type == "platform":
        return get_platform_version(name)

    data = _load()
    for plat_data in data.get("assets", {}).values():
        if isinstance(plat_data, dict):
            version = plat_data.get("devices", {}).get(name)
            if version:
                return version
    return None


def set_asset_version(asset_type: str, name: str, version: str):
    raise NotImplementedError("Use set_platform_version() or set_device_version().")


def get_installed_platforms() -> list[str]:
    data = _load()
    platforms = data.get("installed_agent_platforms", [])
    if not isinstance(platforms, list):
        return []
    return [item for item in platforms if isinstance(item, str) and item.strip()]


def set_installed_platforms(platforms: list):
    data = _load()
    data["installed_agent_platforms"] = [item for item in platforms if isinstance(item, str) and item.strip()]
    _save(data)


def add_installed_platform(platform: str):
    data = _load()
    platforms = data.setdefault("installed_agent_platforms", [])
    if platform not in platforms:
        platforms.append(platform)
    _save(data)


def get_connected_iot_platforms() -> list[str]:
    data = _load()
    platforms = data.get("connected_iot_platforms", [])
    if isinstance(platforms, list):
        normalized = [item for item in platforms if isinstance(item, str) and item.strip()]
        if normalized:
            return normalized
    return []


def set_connected_iot_platforms(platforms: list[str]):
    data = _load()
    data["connected_iot_platforms"] = [item for item in platforms if isinstance(item, str) and item.strip()]
    _save(data)


def add_connected_iot_platform(platform: str):
    data = _load()
    platforms = data.setdefault("connected_iot_platforms", [])
    if platform not in platforms:
        platforms.append(platform)
    _save(data)


def remove_connected_iot_platform(platform: str):
    data = _load()
    platforms = data.get("connected_iot_platforms", [])
    if not isinstance(platforms, list):
        return
    data["connected_iot_platforms"] = [item for item in platforms if item != platform]
    _save(data)


def get_connected_platforms() -> list[str]:
    # Backward-compatible alias for the IoT platform list.
    platforms = get_connected_iot_platforms()
    if platforms:
        return platforms
    return infer_local_iot_platforms()


def infer_local_iot_platforms() -> list[str]:
    data = _load()
    discovered: list[str] = []
    seen: set[str] = set()

    assets = data.get("assets", {})
    if isinstance(assets, dict):
        for key, value in assets.items():
            if not isinstance(key, str) or not key.strip():
                continue
            if not isinstance(value, dict):
                continue
            connector_dir = ASSETS_DIR / key / "connector"
            if connector_dir.exists():
                seen.add(key)
                discovered.append(key)

    if ASSETS_DIR.exists():
        for item in ASSETS_DIR.iterdir():
            if not item.is_dir():
                continue
            if (item / "connector" / "client.py").exists() and item.name not in seen:
                seen.add(item.name)
                discovered.append(item.name)

    return discovered


def ensure_state_migrated(valid_platform_ids: set[str] | None = None) -> dict:
    data = _load()
    changed = False

    connected = data.get("connected_iot_platforms")
    if not isinstance(connected, list):
        connected = []
        data["connected_iot_platforms"] = connected
        changed = True

    normalized_connected: list[str] = []
    seen: set[str] = set()
    valid_ids = {item for item in (valid_platform_ids or set()) if isinstance(item, str) and item}

    for platform in infer_local_iot_platforms():
        if valid_ids and platform not in valid_ids:
            continue
        if platform not in seen:
            seen.add(platform)
            normalized_connected.append(platform)

    for item in connected:
        if not isinstance(item, str) or not item.strip():
            continue
        if valid_ids and item not in valid_ids:
            continue
        if item not in seen:
            seen.add(item)
            normalized_connected.append(item)

    if data.get("connected_iot_platforms") != normalized_connected:
        data["connected_iot_platforms"] = normalized_connected
        changed = True

    assets = data.get("assets", {})
    if isinstance(assets, dict):
        for platform in normalized_connected:
            record = assets.get(platform)
            if not isinstance(record, dict):
                continue
            connector_dir = ASSETS_DIR / platform / "connector"
            if "version" not in record and connector_dir.exists():
                manifest_version = read_local_connector_version(platform)
                if manifest_version:
                    record["version"] = manifest_version
                    changed = True

    if changed:
        _save(data)
    return data


def get_server_version() -> str | None:
    return _load().get("server_version")


def set_server_version(version: str):
    data = _load()
    data["server_version"] = version
    _save(data)


def connector_manifest_path(platform: str) -> Path:
    return ASSETS_DIR / platform / "connector" / "manifest.json"


def read_connector_manifest(platform: str) -> dict | None:
    path = connector_manifest_path(platform)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_connector_manifest(platform: str, version: str, source: str = "download") -> Path:
    path = connector_manifest_path(platform)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "platform_id": platform,
        "version": version,
        "source": source,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def read_local_connector_version(platform: str) -> str | None:
    manifest = read_connector_manifest(platform)
    version = manifest.get("version") if isinstance(manifest, dict) else None
    if isinstance(version, str) and version.strip():
        return version.strip()
    version = get_platform_version(platform)
    if isinstance(version, str) and version.strip():
        return version.strip()
    return None
