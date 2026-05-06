# -*- coding: utf-8 -*-
"""MCP-accessible wrappers for EntroFlow setup commands.

These tools make Docker sidecar deployments usable by agents that can reach
EntroFlow MCP but do not have the local `entroflow` executable in their own
container.
"""
import argparse
import contextlib
import io
from typing import Any, Callable

import cli
from core import config, loader


CliCommand = Callable[[argparse.Namespace], int | None]


def _run_cli(func: CliCommand, namespace: argparse.Namespace) -> str:
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            code = int(func(namespace) or 0)
    except Exception as exc:  # pragma: no cover - defensive boundary for MCP callers
        output = buffer.getvalue().strip()
        if output:
            return f"{output}\nFailed: {exc}"
        return f"Failed: {exc}"

    output = buffer.getvalue().strip()
    if code == 0:
        return output or "OK"
    if output:
        return f"{output}\nCommand exited with status {code}."
    return f"Command exited with status {code}."


def platform_list(query: str = "") -> str:
    """List EntroFlow-supported platforms. Use before connecting a platform."""
    return _run_cli(cli.cmd_list_platforms, argparse.Namespace(query=query or ""))


def platform_connect(
    platform: str,
    url: str = "",
    token: str = "",
    inputs: dict[str, Any] | None = None,
    presentation: str = "file",
    timeout: int = 600,
) -> str:
    """Connect an IoT platform through its connector-defined connection flow.

    This MCP tool is non-blocking. If the connector returns a pending session,
    show the returned QR/file/link to the user and then call platform_connect_poll
    with the returned session_id after the user completes the action.
    """
    platform_id = cli._resolve_platform_or_exit(platform)
    prepared = _prepare_platform_connector(platform_id)
    connector = loader.load_connector(platform_id)
    merged_inputs = _merge_connect_inputs(url, token, inputs)
    args = _connect_namespace(platform_id, merged_inputs, presentation, timeout)
    context = cli._build_connect_context(platform_id, args, merged_inputs)
    result = cli._connector_connect(connector, context)
    status = cli._connect_status(result)
    if status in {"connected", "ok"}:
        config.add_connected_iot_platform(platform_id)
    return _format_connect_tool_result(platform_id, result, prepared, final=status in {"connected", "ok"})


def platform_connect_poll(
    platform: str,
    session_id: str,
    url: str = "",
    token: str = "",
    inputs: dict[str, Any] | None = None,
    presentation: str = "file",
    timeout: int = 600,
) -> str:
    """Poll a pending platform connection session returned by platform_connect."""
    platform_id = cli._resolve_platform_or_exit(platform)
    session_id = str(session_id or "").strip()
    if not session_id:
        return "Missing session_id. Call platform_connect first and pass the returned session_id."
    connector = loader.load_connector(platform_id)
    merged_inputs = _merge_connect_inputs(url, token, inputs)
    args = _connect_namespace(platform_id, merged_inputs, presentation, timeout)
    context = cli._build_connect_context(platform_id, args, merged_inputs)
    result = cli._connector_poll_connect(connector, session_id, context)
    status = cli._connect_status(result)
    if status in {"connected", "ok"}:
        config.add_connected_iot_platform(platform_id)
    return _format_connect_tool_result(platform_id, result, final=status in {"connected", "ok"})


def _prepare_platform_connector(platform: str) -> dict[str, Any]:
    report: dict[str, Any] = {}
    try:
        guide_sync = cli.downloader.download_platform_guide(platform)
        if guide_sync:
            report["guide"] = guide_sync
    except Exception as exc:
        report["guide_error"] = str(exc)

    connector_result = cli._ensure_platform_connector_ready(platform)
    report["connector"] = connector_result
    try:
        refreshed = cli._refresh_platform_devices_table(platform)
        if refreshed:
            report["device_table"] = refreshed
    except Exception as exc:
        report["device_table_error"] = str(exc)
    return report


def _merge_connect_inputs(url: str, token: str, inputs: dict[str, Any] | None) -> dict[str, str]:
    merged: dict[str, str] = {}
    if url:
        merged["url"] = str(url)
    if token:
        merged["token"] = str(token)
    for key, value in (inputs or {}).items():
        if value is None:
            continue
        merged[str(key)] = str(value)
    return merged


def _connect_namespace(platform: str, inputs: dict[str, str], presentation: str, timeout: int) -> argparse.Namespace:
    return argparse.Namespace(
        platform=platform,
        no_prompt=True,
        url=inputs.get("url"),
        token=inputs.get("token"),
        input=[f"{key}={value}" for key, value in inputs.items() if key not in {"url", "token"}],
        presentation=presentation,
        timeout=timeout,
    )


def _format_connect_tool_result(
    platform: str,
    result: dict[str, Any],
    prepared: dict[str, Any] | None = None,
    final: bool = False,
) -> str:
    lines: list[str] = []
    connector = (prepared or {}).get("connector") if prepared else None
    if isinstance(connector, dict):
        connector_status = connector.get("status")
        connector_version = connector.get("version")
        if connector_status and connector_version:
            lines.append(f"connector={connector_status} v{connector_version}")
    device_table = (prepared or {}).get("device_table") if prepared else None
    if isinstance(device_table, dict) and device_table.get("count"):
        lines.append(f"device_table={device_table.get('count')} models")

    status = cli._connect_status(result)
    lines.append(f"status={status or 'unknown'}")
    session_id = str(result.get("session_id") or "").strip()
    if session_id:
        lines.append(f"session_id={session_id}")
    expires_in = result.get("expires_in")
    if expires_in:
        lines.append(f"expires_in={expires_in}")
    message = str(result.get("message") or "").strip()
    if message:
        lines.append(f"message={message}")

    actions = result.get("actions") or []
    if isinstance(actions, list) and actions:
        lines.append("actions:")
        for index, action in enumerate(actions, 1):
            if not isinstance(action, dict):
                continue
            action_type = str(action.get("type") or "instruction").strip()
            lines.append(f"  [{index}] type={action_type}")
            for key in ("message", "file_path", "sidecar_file_path", "url"):
                value = str(action.get(key) or "").strip()
                if value:
                    lines.append(f"      {key}={value}")

    if session_id and not final:
        lines.append(f"next=Show the action to the user, then call platform_connect_poll(platform='{platform}', session_id='{session_id}').")
    return "\n".join(lines) if lines else "OK"


def platform_devices(platform: str = "") -> str:
    """List all devices discovered from connected platforms and their support status. Do not narrow vague user requests to likely candidates; ask the user to choose the exact device_id from the full list."""
    return _run_cli(cli.cmd_list_devices, argparse.Namespace(platform=platform or None))


def device_setup(
    platform: str,
    did: str,
    model: str,
    name: str,
    location: str,
    remark: str,
    version: str = "",
) -> str:
    """Download the device driver and register a discovered device into runtime."""
    return _run_cli(
        cli.cmd_setup,
        argparse.Namespace(
            device=None,
            platform=platform,
            did=did,
            model=model,
            version=version or None,
            name=name,
            location=location,
            remark=remark,
        ),
    )


def entroflow_update() -> str:
    """Update EntroFlow server code, platform connectors, guides, and support tables."""
    return _run_cli(cli.cmd_update, argparse.Namespace())
