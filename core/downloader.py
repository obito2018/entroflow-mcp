# -*- coding: utf-8 -*-
import io
import os
import zipfile
from pathlib import Path

import httpx

from core.config import get_install_id

API_BASE = os.environ.get("ENTROFLOW_API_BASE", "https://entroflow.ai/api")
ASSETS_DIR = Path.home() / ".entroflow" / "assets"


def _params() -> dict:
    return {"install_id": get_install_id()}


def _download_and_extract(url: str, dest: Path):
    resp = httpx.get(url, params=_params(), timeout=30)
    resp.raise_for_status()
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        zf.extractall(dest)


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


def download_platform(platform: str) -> str:
    """下载平台包，解压到 assets/{platform}/connector/，返回版本号。"""
    version = get_platform_latest_version(platform)
    url = f"{API_BASE}/platforms/{platform}/{version}"
    dest = ASSETS_DIR / platform / "connector"
    _download_and_extract(url, dest)
    return version


def download_device(model: str, platform: str) -> str:
    """下载设备包，解压到 assets/{platform}/devices/{model}/，返回版本号。"""
    version = get_device_latest_version(platform, model)
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
            if any(member.startswith(p) for p in ("data/", "runtime/", "config.json")):
                continue
            zf.extract(member, dest)
    return version
