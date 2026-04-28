# -*- coding: utf-8 -*-
from pathlib import Path

from core import config, downloader

ASSETS_DIR = Path.home() / ".entroflow" / "assets"


def _catalog_platform_ids() -> set[str]:
    catalog_path = ASSETS_DIR / "catalog.json"
    if not catalog_path.exists():
        return set()
    try:
        import json

        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    platforms = payload.get("platforms", [])
    if not isinstance(platforms, list):
        return set()
    return {
        str(item.get("id")).strip()
        for item in platforms
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }


def managed_iot_platforms() -> list[str]:
    catalog_ids = _catalog_platform_ids()
    config.ensure_state_migrated(catalog_ids or None)
    platforms = config.get_connected_iot_platforms()
    if platforms:
        return [item for item in platforms if not catalog_ids or item in catalog_ids]
    inferred = config.infer_local_iot_platforms()
    return [item for item in inferred if not catalog_ids or item in catalog_ids]


def _repair_or_install_platform(platform: str) -> tuple[str | None, str]:
    connector_dir = ASSETS_DIR / platform / "connector"
    client_path = connector_dir / "client.py"
    devices_path = connector_dir / f"{platform}_devices.json"
    local_ver = config.read_local_connector_version(platform)

    connector_missing = not client_path.exists()
    devices_missing = not devices_path.exists()
    local_ver_missing = not local_ver

    if connector_missing or devices_missing or local_ver_missing:
        new_ver = downloader.download_platform(platform)
        config.set_platform_version(platform, new_ver)
        config.add_connected_iot_platform(platform)
        reason_parts = []
        if connector_missing:
            reason_parts.append("missing connector")
        if devices_missing:
            reason_parts.append("missing device table")
        if local_ver_missing:
            reason_parts.append("missing version metadata")
        reason = ", ".join(reason_parts) or "self-heal"
        return new_ver, f"repaired ({reason})"

    return local_ver, "installed"


def check_updates() -> str:
    """Check IoT platform/device packages and update newer versions."""
    if not ASSETS_DIR.exists():
        return "No local assets are installed yet."

    platforms = managed_iot_platforms()
    if not platforms:
        return "No managed IoT platforms are installed yet."

    lines = ["Checking updates:"]
    updated = []
    errors = []

    for platform in platforms:
        try:
            local_ver, state = _repair_or_install_platform(platform)
            remote_ver = downloader.get_platform_latest_version(platform)
            if local_ver != remote_ver:
                downloader.download_platform(platform)
                config.set_platform_version(platform, remote_ver)
                lines.append(f"  platform {platform}: {local_ver or 'unknown'} -> {remote_ver} OK")
                updated.append(platform)
            else:
                suffix = f" ({state})" if state != "installed" else ""
                lines.append(f"  platform {platform}: {remote_ver} (up to date){suffix}")
        except Exception as exc:
            lines.append(f"  platform {platform}: check failed ({exc})")
            errors.append(platform)
            continue

        devices_dir = ASSETS_DIR / platform / "devices"
        if not devices_dir.exists():
            continue

        for device_dir in devices_dir.iterdir():
            if not device_dir.is_dir():
                continue

            model = device_dir.name
            local_dv = config.get_device_version(platform, model)
            if not local_dv:
                continue

            try:
                remote_dv = downloader.get_device_latest_version(platform, model)
                if remote_dv and remote_dv != local_dv:
                    downloader.download_device(model, platform)
                    config.set_device_version(platform, model, remote_dv)
                    lines.append(f"    device {model}: {local_dv} -> {remote_dv} OK")
                    updated.append(model)
                else:
                    lines.append(f"    device {model}: {local_dv} (up to date)")
            except Exception as exc:
                lines.append(f"    device {model}: check failed ({exc})")
                errors.append(model)

    if updated:
        lines.append("")
        lines.append(f"Updated {len(updated)} package(s).")
    elif not errors:
        lines.append("")
        lines.append("All packages are up to date.")

    return "\n".join(lines)


def update_server() -> str:
    """Check for a new MCP Server version and update local runtime files."""
    try:
        remote_ver = downloader.get_server_latest_version()
    except Exception as exc:
        return f"Failed to check MCP Server version ({exc})"

    local_ver = config.get_server_version()
    if local_ver == remote_ver:
        return f"MCP Server is already up to date ({local_ver})."

    try:
        new_ver = downloader.download_server()
        config.set_server_version(new_ver)
    except Exception as exc:
        return f"Failed to update MCP Server ({exc})"

    from_str = f"{local_ver} -> " if local_ver else ""
    return (
        f"MCP Server updated ({from_str}{new_ver}).\n"
        "Restart the Agent to use the new version."
    )
