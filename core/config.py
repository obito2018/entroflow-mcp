# -*- coding: utf-8 -*-
import json
import uuid
from pathlib import Path
from typing import Any, Dict

CONFIG_PATH = Path.home() / ".entroflow" / "config.json"


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


def get_platform_version(platform: str) -> str | None:
    return _load().get("assets", {}).get(platform, {}).get("version")


def set_platform_version(platform: str, version: str):
    data = _load()
    data.setdefault("assets", {}).setdefault(platform, {})["version"] = version
    _save(data)


def get_device_version(platform: str, model: str) -> str | None:
    return _load().get("assets", {}).get(platform, {}).get("devices", {}).get(model)


def set_device_version(platform: str, model: str, version: str):
    data = _load()
    assets = data.setdefault("assets", {})
    plat = assets.setdefault(platform, {})
    plat.setdefault("devices", {})[model] = version
    _save(data)


# 兼容旧接口，逐步替换调用方
def get_asset_version(asset_type: str, name: str) -> str | None:
    if asset_type == "platform":
        return get_platform_version(name)
    # device: name 格式为 model，但不知道 platform，扫全部
    data = _load()
    for plat_data in data.get("assets", {}).values():
        if isinstance(plat_data, dict):
            v = plat_data.get("devices", {}).get(name)
            if v:
                return v
    return None


def set_asset_version(asset_type: str, name: str, version: str):
    raise NotImplementedError("请改用 set_platform_version 或 set_device_version")


def get_installed_platforms() -> list:
    return _load().get("installed_agent_platforms", [])


def set_installed_platforms(platforms: list):
    data = _load()
    data["installed_agent_platforms"] = platforms
    _save(data)


def add_installed_platform(platform: str):
    data = _load()
    platforms = data.setdefault("installed_agent_platforms", [])
    if platform not in platforms:
        platforms.append(platform)
    _save(data)


def get_connected_platforms() -> list[str]:
    data = _load()
    platforms = data.get("installed_agent_platforms", [])
    if isinstance(platforms, list) and platforms:
        return [p for p in platforms if isinstance(p, str) and p]

    assets = data.get("assets", {})
    if isinstance(assets, dict):
        return [key for key in assets.keys() if isinstance(key, str) and key]
    return []


def get_server_version() -> str | None:
    return _load().get("server_version")


def set_server_version(version: str):
    data = _load()
    data["server_version"] = version
    _save(data)
