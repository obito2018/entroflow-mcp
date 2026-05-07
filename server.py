# -*- coding: utf-8 -*-
"""
EntroFlow MCP Server
Setup and runtime MCP surface for EntroFlow devices.
"""
import argparse
import os
import sys
from pathlib import Path
from typing import Any, Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP, Image
from mcp.types import TextContent

from tools.device import device_control, device_search, device_status
from tools.setup import (
    device_setup_prepare,
    device_setup,
    entroflow_update,
    platform_connect,
    platform_connect_poll,
    platform_connect_qr as get_platform_connect_qr,
    platform_connect_qr_url,
    platform_devices,
    platform_list,
    platform_select_prepare,
)

Transport = Literal["stdio", "sse", "streamable-http"]
McpMode = Literal["runtime", "setup", "all"]
DEFAULT_HTTP_HOST = "0.0.0.0"
DEFAULT_HTTP_PORT = 8732
DEFAULT_STREAMABLE_HTTP_PATH = "/mcp"
DEFAULT_SSE_PATH = "/sse"
DEFAULT_MESSAGE_PATH = "/messages/"


def _normalize_mode(mode: str | None) -> McpMode:
    value = str(mode or "runtime").strip().lower()
    if value not in {"runtime", "setup", "all"}:
        raise ValueError(f"ENTROFLOW_MCP_MODE must be one of runtime, setup, all; got {mode!r}")
    return value  # type: ignore[return-value]

RUNTIME_INSTRUCTIONS = (
    "EntroFlow connects agents to physical devices.\n"
    "Default MCP mode is runtime-only. Use the local `entroflow` CLI for platform connection, discovery, setup, and update. Docker/OpenClaw sidecar should run with ENTROFLOW_MCP_MODE=all.\n"
    "EntroFlow is the device-control boundary. Platform-native APIs and credentials are for connector-managed connection, discovery, and setup only. Do not bypass EntroFlow by calling Home Assistant or other platform APIs directly to control devices.\n"
    "Do not guess physical device identity from vague phrases. Control only a registered EntroFlow device whose name, location, remark, or device_id clearly matches the user request.\n"
    "Runtime tools:\n"
    "- device_search(query): find registered devices and inspect supported actions.\n"
    "- device_status(device_id): read the current device state.\n"
    "- device_control(device_id, action): execute a runtime action. The action parameter can be a string, an object like {'action': '<supported_action>', 'args': {...}}, or a list of those entries.\n"
    "Before calling device_control for a device, run device_search first and inspect supported_actions. If the device is not returned by device_search, do not control it. Use CLI setup, or sidecar setup MCP tools when ENTROFLOW_MCP_MODE=all."
)

SETUP_INSTRUCTIONS = (
    "EntroFlow setup MCP tools are intended for Docker/OpenClaw sidecar mode, where the agent container may not have the local `entroflow` CLI. Prefer CLI setup whenever CLI is available.\n"
    "Do not default to the previous platform for a new or unregistered device. If the user explicitly named the platform in the current task, use platform_select_prepare(platform, evidence='user_mentioned_platform'). If the platform was just connected, use evidence='just_connected_platform'. Otherwise ask the user which platform to use.\n"
    "Setup tools:\n"
    "- platform_list(query): list supported platforms.\n"
    "- platform_connect(platform, ...): start a connector-defined platform connection flow without blocking for user action.\n"
    "- platform_connect_qr(platform, session_id): return renderable Markdown/public URL plus the QR image for pending scan_qr.\n"
    "- platform_connect_poll(platform, session_id, ...): poll a pending connection session after user action.\n"
    "- platform_select_prepare(platform, evidence): prepare/confirm platform selection and return platform_confirmation_token.\n"
    "- platform_devices(platform, supported_only, platform_confirmation_token): list discovered setup candidates. Use platform='' to list across connected platforms without assuming one.\n"
    "- device_setup_prepare(..., platform_confirmation_token): create a one-time device registration confirmation token after exact physical/logical device and registration fields are known.\n"
    "- device_setup(..., confirmation_token): register the discovered device into runtime only after the user confirms the device_setup_prepare summary.\n"
    "- entroflow_update(): update server code, platform assets, guides, and support tables.\n"
    "For QR login in OpenClaw, prefer Message action='send' with target=<current chat target> and media=<public_url>. Do not send local file paths as chat attachments.\n"
    "After setup, switch back to runtime tools. Never use platform-native APIs for control."
)


def instructions_for_mode(mode: str) -> str:
    normalized = _normalize_mode(mode)
    if normalized == "runtime":
        return RUNTIME_INSTRUCTIONS
    if normalized == "setup":
        return SETUP_INSTRUCTIONS
    return f"{RUNTIME_INSTRUCTIONS}\n\n{SETUP_INSTRUCTIONS}"

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
    parser.add_argument(
        "--mode",
        choices=["runtime", "setup", "all"],
        default=os.environ.get("ENTROFLOW_MCP_MODE", "runtime"),
        help="Tool surface to expose. runtime exposes only device_search/status/control; setup exposes setup tools; all exposes both. Default: runtime, or ENTROFLOW_MCP_MODE.",
    )
    return parser.parse_args(argv)


def create_mcp(args: argparse.Namespace | None = None) -> FastMCP:
    args = args or parse_args([])
    args.mode = _normalize_mode(getattr(args, "mode", "runtime"))
    return FastMCP(
        "EntroFlow",
        instructions=instructions_for_mode(args.mode),
        host=args.host,
        port=args.port,
        streamable_http_path=args.path,
        sse_path=args.sse_path,
        message_path=args.message_path,
    )


def register_runtime_tools(mcp: FastMCP) -> FastMCP:
    mcp.tool()(device_search)
    mcp.tool()(device_status)
    mcp.tool()(device_control)
    return mcp


def register_setup_tools(mcp: FastMCP) -> FastMCP:
    mcp.tool()(platform_list)
    mcp.tool()(platform_connect)

    @mcp.tool()
    def platform_connect_qr(platform: str, session_id: str) -> list[Any]:
        """Return renderable QR instructions and image for a pending platform connection session."""
        qr_bytes = get_platform_connect_qr(platform, session_id)
        public_url = platform_connect_qr_url(platform, session_id, qr_bytes=qr_bytes)
        text = (
            "Show this QR code directly to the user. Prefer sending the Markdown image as-is; "
            "if the chat client cannot render it, send the public_url.\n"
            f"markdown_image=![EntroFlow platform login QR]({public_url})\n"
            f"public_url={public_url}"
        )
        return [TextContent(type="text", text=text), Image(data=qr_bytes, format="png")]

    mcp.tool()(platform_connect_poll)
    mcp.tool()(platform_select_prepare)
    mcp.tool()(platform_devices)
    mcp.tool()(device_setup_prepare)
    mcp.tool()(device_setup)
    mcp.tool()(entroflow_update)
    return mcp


def register_tools(mcp: FastMCP, mode: str = "runtime") -> FastMCP:
    normalized = _normalize_mode(mode)
    if normalized in {"runtime", "all"}:
        register_runtime_tools(mcp)
    if normalized in {"setup", "all"}:
        register_setup_tools(mcp)
    return mcp


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    mcp = register_tools(create_mcp(args), args.mode)
    mcp.run(transport=args.transport)


_default_args = parse_args([])
mcp = register_tools(create_mcp(_default_args), _default_args.mode)


if __name__ == "__main__":
    main()
