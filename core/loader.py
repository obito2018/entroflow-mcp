# -*- coding: utf-8 -*-
import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict

ASSETS_DIR = Path.home() / ".entroflow" / "assets"
RUNTIME_DIR = Path.home() / ".entroflow" / "runtime"

_module_cache: Dict[str, Any] = {}


def _load_module(name: str, file_path: Path):
    if name in _module_cache:
        return _module_cache[name]
    spec = importlib.util.spec_from_file_location(name, str(file_path))
    if not spec or not spec.loader:
        raise ImportError(f"无法加载模块: {file_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    _module_cache[name] = mod
    return mod


def load_connector(platform: str):
    client_path = ASSETS_DIR / platform / "connector" / "mihome_client.py"
    if not client_path.exists():
        raise FileNotFoundError(f"平台 '{platform}' 的连接器不存在，请先调用 platform_install。")
    mod = _load_module(f"ef_connector_{platform}", client_path)
    if hasattr(mod, "set_runtime_dir"):
        mod.set_runtime_dir(RUNTIME_DIR)
    return mod


def load_device_class(platform: str, model: str):
    device_path = ASSETS_DIR / platform / "devices" / model / f"{model}.py"
    if not device_path.exists():
        raise FileNotFoundError(f"设备 '{model}' 的驱动不存在，请先调用 device_install。")
    return _load_module(f"ef_device_{model}", device_path)


def create_device_instance(record: Dict[str, Any]):
    connector = load_connector(record["platform"])
    device_mod = load_device_class(record["platform"], record["model"])
    return device_mod.DeviceClass(did=record["did"], mihome_client=connector)


def load_platform_devices(platform: str):
    """加载平台设备目录文件，返回支持的 model id 集合。"""
    import json
    devices_path = ASSETS_DIR / platform / "connector" / f"{platform}_devices.json"
    if not devices_path.exists():
        raise FileNotFoundError(f"平台 '{platform}' 的设备目录不存在，请先调用 platform_install。")
    data = json.loads(devices_path.read_text(encoding="utf-8"))
    return {item["model"] for item in data if "model" in item}
