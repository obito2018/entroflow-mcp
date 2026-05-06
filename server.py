# -*- coding: utf-8 -*-
"""
EntroFlow MCP Server
Setup and runtime MCP surface for EntroFlow devices.
"""
import argparse
import os
import sys
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP

from tools.device import device_control, device_search, device_status
from tools.setup import device_setup, entroflow_update, platform_connect, platform_devices, platform_list

Transport = Literal["stdio", "sse", "streamable-http"]
DEFAULT_HTTP_HOST = "0.0.0.0"
DEFAULT_HTTP_PORT = 8732
DEFAULT_STREAMABLE_HTTP_PATH = "/mcp"
DEFAULT_SSE_PATH = "/sse"
DEFAULT_MESSAGE_PATH = "/messages/"

INSTRUCTIONS = (
    "EntroFlow connects agents to physical devices.\n"
    "Use local CLI commands when the `entroflow` executable is available. "
    "In Docker sidecar mode, use the MCP setup tools instead.\n"
    "EntroFlow is the device-control boundary. Platform-native APIs and credentials "
    "are for connector-managed connection, discovery, and setup only. Do not bypass "
    "EntroFlow by calling Home Assistant or other platform APIs directly to control devices.\n"
    "Do not guess physical device identity from vague phrases. Control only a registered "
    "EntroFlow device whose name, location, remark, or device_id clearly matches the user request. "
    "If multiple discovered or registered devices could match, ask the user to choose the exact device.\n"
    "Setup tools:\n"
    "- platform_list(query): list supported platforms.\n"
    "- platform_connect(platform, ...): connect a platform through its connector-defined flow.\n"
    "- platform_devices(platform): list discovered platform devices and support status.\n"
    "- device_setup(...): register a discovered device into runtime.\n"
    "- entroflow_update(): update server code, platform assets, guides, and support tables.\n"
    "Runtime tools:\n"
    "- device_search(query): find registered devices and inspect supported actions.\n"
    "- device_status(device_id): read the current device state.\n"
    "- device_control(device_id, action): execute a runtime action.\n"
    "Before calling device_control for a device, run device_search first and inspect supported_actions.\n"
    "If the device is not returned by device_search, do not control it; use platform_devices and device_setup first.\n"
    "For discovered-but-unregistered devices, do not infer aliases such as main light from model or entity names; ask the user to select and set up the exact device.\n"
    "Action names are device-specific by default. Do not assume generic names such as set_power."
)

def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise SystemExit(f"{name} must be an integer, got {raw!r}") from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="entroflow-mcp", description="Run the EntroFlow MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=os.environ.get("ENTROFLOW_MCP_TRANSPORT", "stdio"),
        help="MCP transport to use. Default: stdio, or ENTROFLOW_MCP_TRANSPORT.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("ENTROFLOW_MCP_HOST", DEFAULT_HTTP_HOST),
        help="HTTP bind host for sse or streamable-http. Default: 0.0.0.0.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=_env_int("ENTROFLOW_MCP_PORT", DEFAULT_HTTP_PORT),
        help="HTTP bind port for sse or streamable-http. Default: 8732.",
    )
    parser.add_argument(
        "--path",
        default=os.environ.get("ENTROFLOW_MCP_PATH", DEFAULT_STREAMABLE_HTTP_PATH),
        help="Streamable HTTP MCP path. Default: /mcp.",
    )
    parser.add_argument(
        "--sse-path",
        default=os.environ.get("ENTROFLOW_MCP_SSE_PATH", DEFAULT_SSE_PATH),
        help="SSE endpoint path. Default: /sse.",
    )
    parser.add_argument(
        "--message-path",
        default=os.environ.get("ENTROFLOW_MCP_MESSAGE_PATH", DEFAULT_MESSAGE_PATH),
        help="SSE message endpoint path. Default: /messages/.",
    )
    return parser.parse_args(argv)


def create_mcp(args: argparse.Namespace | None = None) -> FastMCP:
    args = args or parse_args([])
    return FastMCP(
        "EntroFlow",
        instructions=INSTRUCTIONS,
        host=args.host,
        port=args.port,
        streamable_http_path=args.path,
        sse_path=args.sse_path,
        message_path=args.message_path,
    )


def register_tools(mcp: FastMCP) -> FastMCP:
    mcp.tool()(platform_list)
    mcp.tool()(platform_connect)
    mcp.tool()(platform_devices)
    mcp.tool()(device_setup)
    mcp.tool()(entroflow_update)
    mcp.tool()(device_search)
    mcp.tool()(device_status)
    mcp.tool()(device_control)
    return mcp


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    mcp = register_tools(create_mcp(args))
    mcp.run(transport=args.transport)


mcp = register_tools(create_mcp(parse_args([])))


if __name__ == "__main__":
    main()
