# -*- coding: utf-8 -*-
"""MCP-accessible wrappers for EntroFlow setup commands.

These tools make Docker sidecar deployments usable by agents that can reach
EntroFlow MCP but do not have the local `entroflow` executable in their own
container.
"""
import argparse
import contextlib
import io
import os
import secrets
import time
from pathlib import Path
from typing import Any, Callable

import httpx

import cli
from core import config, loader


CliCommand = Callable[[argparse.Namespace], int | None]

_SETUP_CONFIRMATION_TTL_SECONDS = 600
_PLATFORM_SELECTION_TTL_SECONDS = 600
_PLATFORM_EVIDENCE_VALUES = {
    "user_mentioned_platform",
    "just_connected_platform",
    "single_connected_platform",
    "user_confirmed_platform",
}
_PENDING_PLATFORM_SELECTIONS: dict[str, dict[str, Any]] = {}
_PENDING_DEVICE_SETUP_CONFIRMATIONS: dict[str, dict[str, Any]] = {}


def _normalize_platform_selection(platform: str) -> str:
    return str(platform or "").strip()


def _normalize_platform_evidence(evidence: str) -> str:
    return str(evidence or "").strip().lower()


def _platform_evidence_is_valid(evidence: str) -> bool:
    return _normalize_platform_evidence(evidence) in _PLATFORM_EVIDENCE_VALUES


def _prune_expired_platform_selections(now: float | None = None) -> None:
    current = time.time() if now is None else now
    expired = [
        token
        for token, item in _PENDING_PLATFORM_SELECTIONS.items()
        if float(item.get("expires_at") or 0) <= current
    ]
    for token in expired:
        _PENDING_PLATFORM_SELECTIONS.pop(token, None)


def _validate_platform_selection_token(platform: str, token: str) -> str | None:
    normalized_platform = _normalize_platform_selection(platform)
    if not normalized_platform:
        return None
    _prune_expired_platform_selections()
    normalized_token = str(token or "").strip()
    if not normalized_token:
        return "missing platform_confirmation_token"
    pending = _PENDING_PLATFORM_SELECTIONS.get(normalized_token)
    if not pending:
        return "invalid or expired platform_confirmation_token"
    if pending.get("platform") != normalized_platform:
        return "platform_confirmation_token does not match the requested platform"
    return None


def _issue_platform_selection_token(platform_id: str, evidence: str = "") -> str:
    token = secrets.token_urlsafe(18)
    _PENDING_PLATFORM_SELECTIONS[token] = {
        "platform": platform_id,
        "evidence": _normalize_platform_evidence(evidence),
        "expires_at": time.time() + _PLATFORM_SELECTION_TTL_SECONDS,
    }
    return token


def _setup_confirmation_payload(
    platform: str,
    did: str,
    model: str,
    name: str,
    location: str,
    remark: str,
    version: str = "",
) -> dict[str, str]:
    return {
        "platform": str(platform or "").strip(),
        "did": str(did or "").strip(),
        "model": str(model or "").strip(),
        "name": str(name or "").strip(),
        "location": str(location or "").strip(),
        "remark": str(remark or "").strip(),
        "version": str(version or "").strip(),
    }


def _prune_expired_setup_confirmations(now: float | None = None) -> None:
    current = time.time() if now is None else now
    expired = [
        token
        for token, item in _PENDING_DEVICE_SETUP_CONFIRMATIONS.items()
        if float(item.get("expires_at") or 0) <= current
    ]
    for token in expired:
        _PENDING_DEVICE_SETUP_CONFIRMATIONS.pop(token, None)


def _validate_setup_confirmation_token(token: str, payload: dict[str, str]) -> str | None:
    _prune_expired_setup_confirmations()
    normalized_token = str(token or "").strip()
    if not normalized_token:
        return "missing confirmation_token"
    pending = _PENDING_DEVICE_SETUP_CONFIRMATIONS.get(normalized_token)
    if not pending:
        return "invalid or expired confirmation_token"
    if pending.get("payload") != payload:
        return "confirmation_token does not match the submitted registration fields"
    return None


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
    _attach_public_qr_urls(platform_id, connector, result)
    status = cli._connect_status(result)
    if status in {"connected", "ok"}:
        config.add_connected_iot_platform(platform_id)
    return _format_connect_tool_result(platform_id, result, prepared, final=status in {"connected", "ok"})


def _attach_public_qr_urls(platform: str, connector: Any, result: dict[str, Any]) -> None:
    session_id = str(result.get("session_id") or "").strip()
    if not session_id:
        return
    actions = result.get("actions")
    if not isinstance(actions, list):
        return
    has_scan_qr = any(isinstance(action, dict) and str(action.get("type") or "").strip() == "scan_qr" for action in actions)
    if not has_scan_qr:
        return
    try:
        getter = getattr(connector, "get_connect_qr", None)
        if not callable(getter):
            return
        qr_bytes = _coerce_qr_bytes(getter(session_id))
        ttl_seconds = _ttl_from_result(result)
        public_url = _upload_temp_qr(qr_bytes, ttl_seconds)
    except Exception as exc:
        for action in actions:
            if isinstance(action, dict) and str(action.get("type") or "").strip() == "scan_qr":
                action.setdefault("public_url_error", str(exc))
        return
    for action in actions:
        if isinstance(action, dict) and str(action.get("type") or "").strip() == "scan_qr":
            action["public_url"] = public_url
            action["markdown_image"] = f"![EntroFlow platform login QR]({public_url})"
            action["html_image"] = f'<img src="{public_url}" alt="EntroFlow platform login QR" width="320" />'
            action["openclaw_message_send"] = (
                "Use the OpenClaw Message tool with action='send', target=<current chat target>, "
                f"media='{public_url}', and message='请用米家 App 扫描二维码并确认登录'. "
                "Do not omit target and do not send the local file path as plain text."
            )
            action.setdefault("message", "Scan this QR code with the platform app and confirm login.")


def _ttl_from_result(result: dict[str, Any]) -> int:
    try:
        value = int(result.get("expires_in") or 600)
    except (TypeError, ValueError):
        value = 600
    return max(1, min(value, 600))


def _upload_temp_qr(qr_bytes: bytes, ttl_seconds: int) -> str:
    if os.environ.get("ENTROFLOW_DISABLE_PUBLIC_QR_URL", "").strip().lower() in {"1", "true", "yes"}:
        raise RuntimeError("Public QR URL upload is disabled by ENTROFLOW_DISABLE_PUBLIC_QR_URL.")
    api_origin = os.environ.get("ENTROFLOW_PUBLIC_API_ORIGIN", "https://api.entroflow.ai").rstrip("/")
    files = {"file": ("login-qr.png", qr_bytes, "image/png")}
    data = {"ttl_seconds": str(max(1, min(int(ttl_seconds), 600)))}
    with httpx.Client(timeout=10.0) as client:
        resp = client.post(f"{api_origin}/v1/tmp/login-qr", files=files, data=data)
        resp.raise_for_status()
        payload = resp.json()
    public_url = str(payload.get("url") or "").strip()
    if not public_url:
        raise RuntimeError("Temporary QR upload did not return a URL.")
    return public_url


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


def platform_connect_qr(platform: str, session_id: str) -> bytes:
    """Return the QR image for a pending connector login session.

    Use this immediately after platform_connect returns a scan_qr action. This
    avoids relying on agent-specific chat attachment allowlists for local files.
    """
    platform_id = cli._resolve_platform_or_exit(platform)
    session_id = str(session_id or "").strip()
    if not session_id:
        raise ValueError("Missing session_id. Call platform_connect first and pass the returned session_id.")
    connector = loader.load_connector(platform_id)
    getter = getattr(connector, "get_connect_qr", None)
    if callable(getter):
        qr = getter(session_id)
        return _coerce_qr_bytes(qr)
    raise ValueError(f"Platform {platform_id} does not expose a pending QR image for this connection session.")


def platform_connect_qr_url(platform: str, session_id: str, qr_bytes: bytes | None = None) -> str:
    """Return a short-lived public HTTPS URL for a pending connection QR image."""
    platform_id = cli._resolve_platform_or_exit(platform)
    session_id = str(session_id or "").strip()
    if not session_id:
        raise ValueError("Missing session_id. Call platform_connect first and pass the returned session_id.")
    if qr_bytes is None:
        qr_bytes = platform_connect_qr(platform_id, session_id)
    return _upload_temp_qr(qr_bytes, 600)


def _coerce_qr_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        if value:
            return value
        raise ValueError("QR image is empty.")
    if isinstance(value, bytearray):
        data = bytes(value)
        if data:
            return data
        raise ValueError("QR image is empty.")
    if isinstance(value, dict):
        if isinstance(value.get("data"), (bytes, bytearray)):
            return _coerce_qr_bytes(value["data"])
        path = str(value.get("file_path") or value.get("path") or "").strip()
        if path:
            return _read_qr_file(path)
    if isinstance(value, (str, Path)):
        return _read_qr_file(str(value))
    raise ValueError("Connector returned an unsupported QR image payload.")


def _read_qr_file(path: str) -> bytes:
    qr_path = Path(path).expanduser()
    data = qr_path.read_bytes()
    if not data:
        raise ValueError(f"QR image is empty: {qr_path}")
    return data


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
    loader.clear_connector_cache(platform)
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
            for key in (
                "message",
                "openclaw_message_send",
                "markdown_image",
                "public_url",
                "html_image",
                "file_path",
                "sidecar_file_path",
                "url",
                "public_url_error",
            ):
                value = str(action.get(key) or "").strip()
                if value:
                    lines.append(f"      {key}={value}")
            if action_type == "scan_qr" and session_id:
                lines.append(
                    f"      show_qr=On OpenClaw, prefer Message action='send' with target=<current chat target> and media=public_url. If no Message tool is available, send markdown_image or public_url. Otherwise call platform_connect_qr(platform='{platform}', session_id='{session_id}') and show the returned image."
                )

    if session_id and not final:
        lines.append(
            f"next=If a scan_qr action is present on OpenClaw, use the Message tool with action='send', target=<current chat target>, and media=public_url to send the QR image directly. If Message is unavailable, send markdown_image or public_url. Otherwise call platform_connect_qr(platform='{platform}', session_id='{session_id}') and show the returned image. After the user confirms, call platform_connect_poll(platform='{platform}', session_id='{session_id}')."
        )
    return "\n".join(lines) if lines else "OK"


def platform_select_prepare(platform: str, evidence: str = "") -> str:
    """Prepare confirmation for selecting a platform for new-device setup.

    Use this before listing setup candidates for a specific platform when the
    user mentions a new or unregistered device. If the user explicitly named the
    platform in the current task, or just connected this platform, pass evidence
    so a token can be issued without asking again. Otherwise show the returned
    prompt and ask whether the new device is on this platform or another.
    """
    platform_id = _normalize_platform_selection(platform)
    if not platform_id:
        return "Refused: platform is required. Ask the user which platform the new device belongs to."
    try:
        platform_id = cli._resolve_platform_or_exit(platform_id)
    except Exception as exc:
        return f"Refused: unknown platform '{platform}'. Run platform_list first. ({exc})"
    connected = config.get_connected_iot_platforms()
    if connected and platform_id not in connected:
        return (
            f"Refused: platform '{platform_id}' is not connected. Connected platforms: {connected}. "
            "Ask the user whether to connect this platform first or choose another connected platform."
        )

    _prune_expired_platform_selections()
    evidence_id = _normalize_platform_evidence(evidence)
    if evidence and not _platform_evidence_is_valid(evidence):
        return (
            f"Refused: invalid platform evidence '{evidence}'. Valid evidence values: "
            f"{', '.join(sorted(_PLATFORM_EVIDENCE_VALUES))}. If none applies, ask the user to choose the platform."
        )
    token = _issue_platform_selection_token(platform_id, evidence_id)
    connected_text = ", ".join(connected) if connected else "none recorded"
    if evidence_id:
        lines = [
            "Platform selection accepted for new-device setup.",
            f"requested_platform={platform_id}",
            f"platform_confirmed_by={evidence_id}",
            f"connected_platforms={connected_text}",
            f"platform_confirmation_token={token}",
            "next=Use this token with platform_devices and device_setup_prepare. Do not ask the platform question again unless the user changes platform.",
        ]
        return "\n".join(lines)
    lines = [
        "Platform selection confirmation required for new-device setup.",
        f"requested_platform={platform_id}",
        f"connected_platforms={connected_text}",
        "Ask the user: Is this new device on the requested platform, or should we use another platform?",
        f"platform_confirmation_token={token}",
        "next=Only after the user explicitly confirms this platform, call platform_devices with platform and this platform_confirmation_token. If the user chooses another platform, run platform_select_prepare for that platform instead.",
    ]
    return "\n".join(lines)


def platform_devices(platform: str = "", supported_only: bool = True, platform_confirmation_token: str = "") -> str:
    """List setup candidates from connected platforms.

    Default to supported_only=True for chat agents: show only EntroFlow-supported,
    setup-relevant logical devices. Do not list every Home Assistant entity or ask
    the user to choose among sibling entities of the same physical device. For a
    specific new-device setup platform, call platform_select_prepare first and
    pass its platform_confirmation_token after the user confirms the platform.
    """
    platform_id = _normalize_platform_selection(platform)
    token_error = _validate_platform_selection_token(platform_id, platform_confirmation_token)
    if token_error:
        return (
            f"Refused: platform_devices for a specific platform requires platform confirmation ({token_error}). "
            "Do not default to the previous platform for a new device. Call platform_select_prepare(platform), "
            "ask whether the new device is on that platform or another platform, then retry with the returned token. "
            "Alternatively call platform_devices(platform='') to list candidates across all connected platforms."
        )
    return _run_cli(
        cli.cmd_list_devices,
        argparse.Namespace(platform=platform_id or None, supported_only=supported_only),
    )


def device_setup_prepare(
    platform: str,
    did: str,
    model: str,
    name: str,
    location: str,
    remark: str,
    version: str = "",
    platform_confirmation_token: str = "",
) -> str:
    """Prepare a device setup confirmation summary and one-time token.

    Call this after the platform was confirmed with platform_select_prepare, and
    after the user selects the exact physical/logical device and has provided
    name, location, and remark. Show the returned summary to the user and ask
    them to confirm. Only after the user confirms may device_setup be called
    with the returned confirmation_token.
    """
    payload = _setup_confirmation_payload(platform, did, model, name, location, remark, version)
    missing = [key for key in ("platform", "did", "model", "name", "location", "remark") if not payload[key]]
    if missing:
        return f"Refused: missing registration field(s): {', '.join(missing)}. Ask the user before setup."
    platform_error = _validate_platform_selection_token(payload["platform"], platform_confirmation_token)
    if platform_error:
        return (
            f"Refused: device_setup_prepare requires platform confirmation ({platform_error}). "
            "Call platform_select_prepare first. If the user explicitly named the platform in the current task, "
            "pass evidence='user_mentioned_platform'; if the platform was just connected, pass evidence='just_connected_platform'. "
            "Then pass the returned platform_confirmation_token here."
        )

    _prune_expired_setup_confirmations()
    token = secrets.token_urlsafe(18)
    _PENDING_DEVICE_SETUP_CONFIRMATIONS[token] = {
        "payload": payload,
        "expires_at": time.time() + _SETUP_CONFIRMATION_TTL_SECONDS,
    }

    lines = [
        "Device setup confirmation required.",
        "Show this exact registration summary to the user and wait for explicit confirmation before setup:",
        f"platform={payload['platform']}",
        f"did={payload['did']}",
        f"model={payload['model']}",
        f"name={payload['name']}",
        f"location={payload['location']}",
        f"remark={payload['remark']}",
    ]
    if payload["version"]:
        lines.append(f"version={payload['version']}")
    lines.extend(
        [
            f"confirmation_token={token}",
            "next=After the user explicitly confirms this summary, call device_setup with the same fields and this confirmation_token. Do not call device_setup before that confirmation.",
        ]
    )
    return "\n".join(lines)


def device_setup(
    platform: str,
    did: str,
    model: str,
    name: str,
    location: str,
    remark: str,
    version: str = "",
    confirmed: bool = False,
    confirmation_token: str = "",
) -> str:
    """Download the device driver and register a discovered device into runtime.

    Call this only after device_setup_prepare returned a confirmation_token and
    the user explicitly confirmed the exact summary containing platform,
    device_id/did, model, name, location, and remark. The token is one-time and
    only valid for the same registration fields.
    """
    payload = _setup_confirmation_payload(platform, did, model, name, location, remark, version)
    token_error = _validate_setup_confirmation_token(confirmation_token, payload)
    if token_error:
        return (
            f"Refused: device_setup requires a valid confirmation_token ({token_error}). "
            "Call device_setup_prepare with the exact platform, device_id/did, model, name, "
            "location, and remark; show the returned summary to the user; wait for explicit "
            "confirmation; then call device_setup with that token. Do not infer or invent "
            "registration metadata."
        )
    _PENDING_DEVICE_SETUP_CONFIRMATIONS.pop(str(confirmation_token).strip(), None)
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
            confirmed=True,
        ),
    )


def entroflow_update() -> str:
    """Update EntroFlow server code, platform connectors, guides, and support tables."""
    return _run_cli(cli.cmd_update, argparse.Namespace())
