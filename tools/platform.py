# -*- coding: utf-8 -*-
import json
from pathlib import Path

from core import config

ASSETS_DIR = Path.home() / ".entroflow" / "assets"
CATALOG_FILE = ASSETS_DIR / "catalog.json"


def _load_catalog() -> list:
    """读取平台目录，返回 platforms 列表。"""
    if not CATALOG_FILE.exists():
        return []
    with open(CATALOG_FILE, encoding="utf-8") as f:
        return json.load(f).get("platforms", [])


def resolve_platform(name: str) -> tuple[str | None, str | None]:
    """将用户输入解析为平台 id。返回 (platform_id, error_message)。"""
    name_lower = name.lower().strip()
    catalog = _load_catalog()
    for entry in catalog:
        candidates = [entry["id"], entry.get("display_name", "")] + entry.get("aliases", [])
        if name_lower in [c.lower() for c in candidates]:
            return entry["id"], None
    # catalog 为空或未匹配，直接透传（兼容 Phase 1 本地模式）
    if not catalog:
        return name, None
    ids = ", ".join(e["id"] for e in catalog)
    names = ", ".join(f"{e['id']}（{e['display_name']}）" for e in catalog)
    return None, f"未找到平台 '{name}'。可用平台：{names}"


def platform_install(platform: str) -> str:
    """下载并安装指定平台的连接包。包含平台登录代码和支持的设备列表。
    首次使用某平台前必须先调用此工具。可用平台见 entroflow.io/devices。"""
    from core import downloader

    platform_id, err = resolve_platform(platform)
    if err:
        return err

    connector_dir = ASSETS_DIR / platform_id / "connector"
    devices_file = connector_dir / f"{platform_id}_devices.json"

    # 已安装且完整，跳过
    if connector_dir.exists() and devices_file.exists() and any(connector_dir.glob("*_client.py")):
        return f"平台 '{platform_id}' 已就绪。"

    try:
        version = downloader.download_platform(platform_id)
        config.set_platform_version(platform_id, version)
        return f"平台 '{platform_id}' 安装成功（version={version}）。"
    except Exception as e:
        return f"平台 '{platform_id}' 安装失败: {e}"


def platform_list() -> str:
    """列出所有可用平台及安装状态。在调用 platform_install 前先调用此工具确认平台 id。"""
    catalog = _load_catalog()

    if not catalog:
        # 无 catalog，降级为扫目录
        if not ASSETS_DIR.exists():
            return "尚未安装任何平台包。"
        lines = []
        for d in ASSETS_DIR.iterdir():
            if not d.is_dir():
                continue
            version = config.get_platform_version(d.name) or "unknown"
            devices_dir = d / "devices"
            count = sum(1 for x in devices_dir.iterdir() if x.is_dir()) if devices_dir.exists() else 0
            lines.append(f"  {d.name}  version={version}  已安装设备驱动={count}")
        return ("已安装平台：\n" + "\n".join(lines)) if lines else "尚未安装任何平台包。"

    lines = ["可用平台：\n"]
    for entry in catalog:
        pid = entry["id"]
        display = entry["display_name"]
        desc = entry.get("description", "")
        version = config.get_platform_version(pid)
        installed = version is not None
        status = f"已安装 version={version}" if installed else "未安装"
        devices_dir = ASSETS_DIR / pid / "devices"
        count = sum(1 for x in devices_dir.iterdir() if x.is_dir()) if devices_dir.exists() else 0
        device_info = f"  已安装设备驱动={count}" if installed else ""
        lines.append(f"  {pid}（{display}）— {desc}")
        lines.append(f"    状态: {status}{device_info}")
        lines.append("")

    return "\n".join(lines)
