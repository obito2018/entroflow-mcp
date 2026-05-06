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

    The default presentation is file so remote/chat agents get local QR files or
    other transferable artifacts instead of a browser-only localhost flow.
    """
    input_items = []
    for key, value in (inputs or {}).items():
        if value is None:
            continue
        input_items.append(f"{key}={value}")

    return _run_cli(
        cli.cmd_connect,
        argparse.Namespace(
            platform=platform,
            no_prompt=True,
            url=url or None,
            token=token or None,
            input=input_items,
            presentation=presentation,
            timeout=timeout,
        ),
    )


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
