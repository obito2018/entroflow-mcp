# -*- coding: utf-8 -*-
import importlib.util
import inspect
import json
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
        raise ImportError(f"Cannot load module: {file_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    _module_cache[name] = mod
    return mod


def _resolve_connector_path(platform: str) -> Path:
    connector_dir = ASSETS_DIR / platform / "connector"
    candidates = [
        connector_dir / "client.py",
        connector_dir / f"{platform}_client.py",
        connector_dir / "mihome_client.py",
    ]

    for path in candidates:
        if path.exists():
            return path

    legacy_matches = sorted(connector_dir.glob("*_client.py"))
    if legacy_matches:
        return legacy_matches[0]

    raise FileNotFoundError(
        f"Platform '{platform}' is not connected. Run `entroflow connect {platform}` first."
    )


def load_connector(platform: str):
    client_path = _resolve_connector_path(platform)
    mod = _load_module(f"ef_connector_{platform}", client_path)
    if hasattr(mod, "set_runtime_dir"):
        mod.set_runtime_dir(RUNTIME_DIR)
    return mod


def load_device_class(platform: str, model: str):
    device_path = ASSETS_DIR / platform / "devices" / model / f"{model}.py"
    if not device_path.exists():
        raise FileNotFoundError(
            f"Device '{model}' is not set up. Run `entroflow setup --platform {platform} --model {model} ...` first."
        )
    return _load_module(f"ef_device_{model}", device_path)


def list_connector_devices(connector):
    if hasattr(connector, "list_devices"):
        return connector.list_devices()
    if hasattr(connector, "list_mihome_devices"):
        return connector.list_mihome_devices()
    raise AttributeError("Connector does not expose a supported device listing method.")


def _build_device_kwargs(device_cls, did: str, connector):
    signature = inspect.signature(device_cls.__init__)
    params = signature.parameters

    kwargs: Dict[str, Any] = {"did": did}
    if "connector" in params:
        kwargs["connector"] = connector
    elif "client" in params:
        kwargs["client"] = connector
    elif "mihome_client" in params:
        kwargs["mihome_client"] = connector
    else:
        return {}
    return kwargs


def create_device_instance(record: Dict[str, Any]):
    connector = load_connector(record["platform"])
    device_mod = load_device_class(record["platform"], record["model"])
    device_cls = device_mod.DeviceClass
    kwargs = _build_device_kwargs(device_cls, record["did"], connector)
    if kwargs:
        return device_cls(**kwargs)
    return device_cls(record["did"], connector)


def load_platform_devices(platform: str):
    devices_path = ASSETS_DIR / platform / "connector" / f"{platform}_devices.json"
    if not devices_path.exists():
        raise FileNotFoundError(
            f"Platform catalog for '{platform}' is missing. Run `entroflow connect {platform}` first."
        )
    data = json.loads(devices_path.read_text(encoding="utf-8"))
    return {item["model"] for item in data if "model" in item}
