# -*- coding: utf-8 -*-
from pathlib import Path

from core import config, downloader

ASSETS_DIR = Path.home() / ".entroflow" / "assets"


def check_updates() -> str:
    """Check installed platform/device packages and download newer versions when available."""
    if not ASSETS_DIR.exists():
        return "No local assets are installed yet."

    lines = ["Checking updates:"]
    updated = []
    errors = []

    for platform_dir in ASSETS_DIR.iterdir():
        if not platform_dir.is_dir() or platform_dir.name == "__pycache__":
            continue

        platform = platform_dir.name
        local_ver = config.get_platform_version(platform)
        if not local_ver:
            continue

        try:
            remote_ver = downloader.get_platform_latest_version(platform)
            if remote_ver and remote_ver != local_ver:
                downloader.download_platform(platform)
                config.set_platform_version(platform, remote_ver)
                lines.append(f"  platform {platform}: {local_ver} -> {remote_ver} OK")
                updated.append(platform)
            else:
                lines.append(f"  platform {platform}: {local_ver} (up to date)")
        except Exception as exc:
            lines.append(f"  platform {platform}: check failed ({exc})")
            errors.append(platform)

        devices_dir = platform_dir / "devices"
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
        lines.append(f"")
        lines.append(f"Updated {len(updated)} package(s).")
    elif not errors:
        lines.append("")
        lines.append("All packages are up to date.")

    return "\n".join(lines)


def update_server() -> str:
    """Check for a new MCP Server version and update the local runtime files."""
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
