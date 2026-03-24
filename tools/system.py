# -*- coding: utf-8 -*-
from pathlib import Path

from core import config, downloader

ASSETS_DIR = Path.home() / ".entroflow" / "assets"


def check_updates() -> str:
    """检查已安装的平台包和设备包是否有新版本，有则自动下载更新。"""
    if not ASSETS_DIR.exists():
        return "尚未安装任何资产包。"

    lines = ["检查更新："]
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
                lines.append(f"  平台 {platform}: {local_ver} → {remote_ver} ✓")
                updated.append(platform)
            else:
                lines.append(f"  平台 {platform}: {local_ver}（已是最新）")
        except Exception as e:
            lines.append(f"  平台 {platform}: 检查失败 ({e})")
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
                    lines.append(f"    设备 {model}: {local_dv} → {remote_dv} ✓")
                    updated.append(model)
                else:
                    lines.append(f"    设备 {model}: {local_dv}（已是最新）")
            except Exception as e:
                lines.append(f"    设备 {model}: 检查失败 ({e})")
                errors.append(model)

    if updated:
        lines.append(f"\n已更新 {len(updated)} 个包。")
    elif not errors:
        lines.append("\n所有包均为最新版本。")

    return "\n".join(lines)

