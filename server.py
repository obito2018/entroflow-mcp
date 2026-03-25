# -*- coding: utf-8 -*-
"""
EntroFlow MCP Server
连接 AI Agent 与智能设备的开放协议层。支持智能家居、机器人、机械臂及其他智能硬件。
"""
import sys
from pathlib import Path

# 确保 ~/.entroflow 在 Python 路径里，tools/core 模块才能正确 import
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP

from tools.device import device_search, device_status, device_control, device_register
from tools.platform import platform_install, platform_list
from tools.login import login_start, login_poll
from tools.discovery import device_discover, device_install
from tools.system import check_updates

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
mcp = FastMCP(
    "EntroFlow",
    instructions=(
        "EntroFlow 是智能设备控制工具，支持智能家居、机器人、机械臂及其他智能硬件。"
        "使用指南见本地文件 ~/.entroflow/skill.md。\n"
        "控制设备前先用 device_search 查找设备；"
        "首次使用需先调用 platform_install 安装平台包，完成登录和设备注册。"
    ),
)

# 注册所有工具
mcp.tool()(device_search)
mcp.tool()(device_status)
mcp.tool()(device_control)
mcp.tool()(device_register)
mcp.tool()(platform_install)
mcp.tool()(platform_list)
mcp.tool()(login_start)
mcp.tool()(login_poll)
mcp.tool()(device_discover)
mcp.tool()(device_install)
mcp.tool()(check_updates)

# ---------------------------------------------------------------------------
# 启动
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run(transport="stdio")
