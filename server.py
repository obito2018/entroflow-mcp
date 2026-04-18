# -*- coding: utf-8 -*-
"""
EntroFlow MCP Server
Runtime-only MCP surface for already connected and set up devices.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP

from tools.device import device_control, device_search, device_status


mcp = FastMCP(
    "EntroFlow",
    instructions=(
        "EntroFlow exposes runtime device operations only.\n"
        "Use the local guide at ~/.entroflow/skill.md for setup and CLI workflows.\n"
        "Before using runtime tools, make sure the user has already connected a platform "
        "with `entroflow connect <platform>` and completed device setup with "
        "`entroflow setup ...`.\n"
        "Runtime tools:\n"
        "- device_search(query): find registered devices and inspect supported actions.\n"
        "- device_status(device_id): read the current device state.\n"
        "- device_control(device_id, action): execute a runtime action.\n"
        "Action names are driver-specific. Inspect supported_actions from device_search before calling device_control.\n"
        "Do not attempt installation, login, discovery, or updates through MCP."
    ),
)

mcp.tool()(device_search)
mcp.tool()(device_status)
mcp.tool()(device_control)


if __name__ == "__main__":
    mcp.run(transport="stdio")
