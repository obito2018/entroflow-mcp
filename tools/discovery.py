# -*- coding: utf-8 -*-
from pathlib import Path

from core import config, loader

ASSETS_DIR = Path.home() / ".entroflow" / "assets"


def device_discover(platform: str) -> str:
    """拉取用户在指定平台的设备列表，与本地 devices.json 匹配，返回有驱动支持的设备。
    需先完成登录。纯本地匹配，不联网。"""
    try:
        connector = loader.load_connector(platform)
        user_devices = connector.list_mihome_devices()
    except Exception as e:
        return f"拉取设备列表失败: {e}"

    if not user_devices:
        return "未发现任何设备。"

    try:
        supported_models = loader.load_platform_devices(platform)
    except FileNotFoundError as e:
        return str(e)

    supported = []
    unsupported = []
    for d in user_devices:
        model = d.get("model", "")
        entry = {
            "did": d.get("did", "?"),
            "name": d.get("name", "?"),
            "model": model,
        }
        if model in supported_models:
            supported.append(entry)
        else:
            unsupported.append(entry)

    lines = [f"发现 {len(user_devices)} 个设备，其中 {len(supported)} 个 EntroFlow 支持：\n"]

    if supported:
        lines.append("【支持】")
        for i, d in enumerate(supported, 1):
            lines.append(f"  [{i}] name={d['name']}  did={d['did']}  model={d['model']}")
        lines.append("")

    if unsupported:
        lines.append("【暂不支持】")
        for d in unsupported:
            lines.append(f"  - name={d['name']}  model={d['model']}")
        lines.append("")
        lines.append("如需支持更多设备，请访问 entroflow.io/submit 提交需求。")

    if supported:
        lines.append("\n要注册设备，请依次调用 device_install 和 device_register。")

    return "\n".join(lines)


def device_install(model: str, platform: str) -> str:
    """下载并安装指定设备的驱动包。包含控制脚本、说明文档和 spec 文档。
    在 device_register 之前必须先调用此工具。"""
    from core import downloader

    device_dir = ASSETS_DIR / platform / "devices" / model
    script_path = device_dir / f"{model}.py"

    # 已安装，跳过
    if script_path.exists():
        return f"设备 '{model}' 驱动已存在，无需重复安装。"

    try:
        version = downloader.download_device(model, platform)
        config.set_device_version(platform, model, version)
        return f"设备 '{model}' 驱动安装成功（version={version}）。"
    except Exception as e:
        return f"设备 '{model}' 驱动安装失败: {e}"
