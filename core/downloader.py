# -*- coding: utf-8 -*-
import io
import json
import locale
import os
import zipfile
from pathlib import Path

import httpx

from core.config import get_install_id, write_connector_manifest

API_BASE = os.environ.get("ENTROFLOW_API_BASE", "https://api.entroflow.ai/api")
ASSETS_DIR = Path.home() / ".entroflow" / "assets"
CATALOG_PATH = ASSETS_DIR / "catalog.json"
PLATFORM_DOCS_DIR = Path.home() / ".entroflow" / "docs" / "platforms"


def _params() -> dict:
    return {"install_id": get_install_id()}


def _download_and_extract(url: str, dest: Path):
    resp = httpx.get(url, params=_params(), timeout=30)
    resp.raise_for_status()
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        zf.extractall(dest)


def _platform_connector_dir(platform: str) -> Path:
    return ASSETS_DIR / platform / "connector"


def _platform_devices_path(platform: str) -> Path:
    return _platform_connector_dir(platform) / f"{platform}_devices.json"


def get_platform_latest_version(platform: str) -> str:
    url = f"{API_BASE}/platforms/{platform}/latest"
    resp = httpx.get(url, params=_params(), timeout=10)
    resp.raise_for_status()
    return resp.json()["version"]


def get_device_latest_version(platform: str, model: str) -> str:
    url = f"{API_BASE}/platforms/{platform}/devices/{model}/latest"
    resp = httpx.get(url, params=_params(), timeout=10)
    resp.raise_for_status()
    return resp.json()["version"]


def fetch_platform_devices_file(platform: str) -> list[dict]:
    url = f"{API_BASE}/platforms/{platform}/{platform}_devices.json"
    resp = httpx.get(url, params=_params(), timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    if not isinstance(payload, list):
        raise ValueError(f"Platform device table for '{platform}' must be a list.")
    return payload


def refresh_platform_devices_file(platform: str) -> dict:
    payload = fetch_platform_devices_file(platform)
    connector_dir = _platform_connector_dir(platform)
    connector_dir.mkdir(parents=True, exist_ok=True)
    devices_path = _platform_devices_path(platform)
    devices_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return {
        "platform_id": platform,
        "path": str(devices_path),
        "count": len(payload),
    }


def download_platform(platform: str) -> str:
    """下载平台包，解压到 assets/{platform}/connector/，并刷新设备支持表。"""
    version = get_platform_latest_version(platform)
    url = f"{API_BASE}/platforms/{platform}/{version}"
    dest = _platform_connector_dir(platform)
    _download_and_extract(url, dest)
    refresh_platform_devices_file(platform)
    write_connector_manifest(platform, version, source="download")
    return version


def download_device(model: str, platform: str, version: str | None = None) -> str:
    """下载设备包，解压到 assets/{platform}/devices/{model}/，返回版本号。"""
    version = version or get_device_latest_version(platform, model)
    url = f"{API_BASE}/platforms/{platform}/devices/{model}/{version}"
    dest = ASSETS_DIR / platform / "devices" / model
    _download_and_extract(url, dest)
    return version


def fetch_catalog() -> dict:
    """从服务器拉取 catalog.json。"""
    url = f"{API_BASE}/catalog"
    resp = httpx.get(url, params=_params(), timeout=10)
    resp.raise_for_status()
    return resp.json()


def refresh_catalog() -> dict:
    catalog = fetch_catalog()
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return catalog


def _guide_manifest_path(platform: str) -> Path:
    return PLATFORM_DOCS_DIR / f"{platform}.manifest.json"


def _guide_markdown_path(platform: str) -> Path:
    return PLATFORM_DOCS_DIR / f"{platform}.md"


def _read_cached_guide_manifest(platform: str) -> dict | None:
    path = _guide_manifest_path(platform)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _preferred_guide_locale() -> str:
    lang, _encoding = locale.getdefaultlocale()
    if isinstance(lang, str) and lang.lower().startswith("zh"):
        return "zh"
    return "en"


def get_platform_guide_latest(platform: str) -> dict | None:
    url = f"{API_BASE}/platform-guides/{platform}/latest"
    resp = httpx.get(url, params=_params(), timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def download_platform_guide(platform: str, preferred_locale: str = "auto") -> dict | None:
    manifest = get_platform_guide_latest(platform)
    if not manifest:
        return None

    locales = [str(item).strip() for item in manifest.get("locales", []) if str(item).strip()]
    if not locales:
        return None

    preferred = _preferred_guide_locale() if preferred_locale == "auto" else preferred_locale.strip().lower()
    selected_locale = preferred if preferred in locales else ("en" if "en" in locales else locales[0])
    cached_manifest = _read_cached_guide_manifest(platform)
    guide_path = _guide_markdown_path(platform)
    manifest_path = _guide_manifest_path(platform)

    if (
        cached_manifest
        and cached_manifest.get("version") == manifest.get("version")
        and cached_manifest.get("selected_locale") == selected_locale
        and guide_path.exists()
    ):
        return {
            "status": "cached",
            "platform_id": platform,
            "version": manifest.get("version"),
            "locale": selected_locale,
            "path": str(guide_path),
        }

    url = f"{API_BASE}/platform-guides/{platform}/{manifest['version']}/{selected_locale}"
    resp = httpx.get(url, params=_params(), timeout=10)
    resp.raise_for_status()

    PLATFORM_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    guide_path.write_text(resp.text, encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                **manifest,
                "selected_locale": selected_locale,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return {
        "status": "synced",
        "platform_id": platform,
        "version": manifest.get("version"),
        "locale": selected_locale,
        "path": str(guide_path),
    }


def refresh_platform_guides(platforms: list[str], preferred_locale: str = "auto") -> list[dict]:
    results: list[dict] = []
    seen: set[str] = set()

    for raw_platform in platforms:
        platform = str(raw_platform).strip()
        if not platform or platform in seen:
            continue
        seen.add(platform)
        try:
            synced = download_platform_guide(platform, preferred_locale=preferred_locale)
            if synced:
                results.append(synced)
            else:
                results.append({
                    "status": "missing",
                    "platform_id": platform,
                })
        except Exception as exc:
            results.append({
                "status": "error",
                "platform_id": platform,
                "error": str(exc),
            })

    return results


def get_server_latest_version() -> str:
    """获取 MCP Server 最新版本号。"""
    url = f"{API_BASE}/server/latest"
    resp = httpx.get(url, params=_params(), timeout=10)
    resp.raise_for_status()
    return resp.json()["version"]


def download_server() -> str:
    """下载最新 MCP Server 代码，覆盖本地文件，返回版本号。"""
    version = get_server_latest_version()
    url = f"{API_BASE}/server/{version}"
    dest = Path.home() / ".entroflow"
    resp = httpx.get(url, params=_params(), timeout=60)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        for member in zf.namelist():
            # 只覆盖代码文件，跳过用户数据
            if any(member.startswith(p) for p in ("data/", "runtime/", "config.json", "assets/catalog.json")):
                continue
            zf.extract(member, dest)
    return version
