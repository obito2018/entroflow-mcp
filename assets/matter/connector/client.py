# -*- coding: utf-8 -*-
import html
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

import websocket


RUNTIME_DIR: Optional[Path] = None
LOGIN_SESSIONS: Dict[str, "MatterLoginSession"] = {}
LOGIN_SESSIONS_LOCK = threading.Lock()

DEFAULT_WS_PORT = 5580
DEFAULT_TIMEOUT = 20

DESCRIPTOR_CLUSTER_ID = 0x001D
BASIC_INFORMATION_CLUSTER_ID = 0x0028
ON_OFF_CLUSTER_ID = 0x0006
LEVEL_CONTROL_CLUSTER_ID = 0x0008
DOOR_LOCK_CLUSTER_ID = 0x0101
THERMOSTAT_CLUSTER_ID = 0x0201
COLOR_CONTROL_CLUSTER_ID = 0x0300
OCCUPANCY_SENSING_CLUSTER_ID = 0x0406
BOOLEAN_STATE_CLUSTER_ID = 0x0045


SUPPORTED_DEVICE_TYPE_MODELS = {
    0x010C: "matter.light.color_temperature",
    0x010D: "matter.light.color_temperature",
    0x0101: "matter.light.dimmable",
    0x0100: "matter.light.on_off",
    0x010A: "matter.smart_plug",
    0x010B: "matter.smart_plug",
    0x000A: "matter.lock",
    0x0301: "matter.thermostat",
    0x0107: "matter.sensor.occupancy",
    0x0015: "matter.sensor.contact",
}

SUPPORTED_DEVICE_TYPE_NAMES = {
    "matter.light.on_off": "Matter On/Off Light",
    "matter.light.dimmable": "Matter Dimmable Light",
    "matter.light.color_temperature": "Matter Color Temperature Light",
    "matter.smart_plug": "Matter Smart Plug",
    "matter.lock": "Matter Door Lock",
    "matter.thermostat": "Matter Thermostat",
    "matter.sensor.occupancy": "Matter Occupancy Sensor",
    "matter.sensor.contact": "Matter Contact Sensor",
}


@dataclass
class MatterConfig:
    ws_url: str
    api_token: str | None
    updated_at: str


@dataclass
class MatterLoginSession:
    session_id: str
    form_url: str
    timeout: int
    created_at: float
    server: ThreadingHTTPServer
    server_thread: threading.Thread
    status: str = "waiting"
    message: str = ""
    last_error: str = ""
    submitted_at: Optional[float] = None
    metadata: Dict[str, str] = field(default_factory=dict)


def set_runtime_dir(path: Path) -> None:
    global RUNTIME_DIR
    RUNTIME_DIR = path
    path.mkdir(parents=True, exist_ok=True)


def _get_runtime_dir() -> Path:
    if RUNTIME_DIR is None:
        raise RuntimeError("Runtime directory is not set. Call set_runtime_dir() first.")
    return RUNTIME_DIR


def _auth_path() -> Path:
    return _get_runtime_dir() / "matter_server.json"


def _now_string() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _normalize_ws_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise ValueError("Matter Server WebSocket URL is required.")

    if "://" not in raw:
        raw = f"ws://{raw}"

    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()
    if scheme not in {"ws", "wss", "http", "https"}:
        raise ValueError("Matter Server URL must use ws, wss, http, or https.")
    if not parsed.netloc:
        raise ValueError("Matter Server URL is invalid.")

    normalized_scheme = {"http": "ws", "https": "wss"}.get(scheme, scheme)
    path = parsed.path or ""
    if path in {"", "/"}:
        path = "/ws"
    return f"{normalized_scheme}://{parsed.netloc}{path}"


def _build_ws_headers(api_token: Optional[str]) -> List[str]:
    headers: List[str] = []
    token = (api_token or "").strip()
    if token:
        headers.append(f"Authorization: Bearer {token}")
    return headers


def _load_auth_file() -> Optional[Dict[str, Any]]:
    path = _auth_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _save_auth_file(config: MatterConfig) -> None:
    _auth_path().write_text(json.dumps(config.__dict__, indent=2), encoding="utf-8")


def get_matter_config(override: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    override = override or {}
    ws_url = override.get("ws_url") or override.get("url")
    api_token = override.get("api_token") or override.get("token")
    if ws_url:
        return {
            "ws_url": _normalize_ws_url(ws_url),
            "api_token": (api_token or "").strip(),
        }

    stored = _load_auth_file()
    if stored and stored.get("ws_url"):
        return {
            "ws_url": _normalize_ws_url(str(stored["ws_url"])),
            "api_token": str(stored.get("api_token") or ""),
        }

    raise ValueError("Matter is not connected yet. Run `entroflow connect matter` first.")


def _recv_json(ws: websocket.WebSocket) -> Dict[str, Any]:
    raw = ws.recv()
    if not isinstance(raw, str):
        raise RuntimeError("Matter Server returned a non-text WebSocket message.")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Matter Server returned invalid JSON.") from exc


def _connect_socket(ws_url: str, api_token: Optional[str], timeout: int) -> tuple[websocket.WebSocket, Dict[str, Any]]:
    ws = websocket.create_connection(
        ws_url,
        timeout=timeout,
        header=_build_ws_headers(api_token),
        enable_multithread=True,
    )
    server_info = _recv_json(ws)
    if "schema_version" not in server_info:
        ws.close()
        raise RuntimeError("Matter Server did not send a valid server_info message.")
    return ws, server_info


def _rpc(command: str, timeout: int = DEFAULT_TIMEOUT, override: Optional[Dict[str, str]] = None, **kwargs: Any) -> Any:
    config = get_matter_config(override)
    ws, _server_info = _connect_socket(config["ws_url"], config.get("api_token"), timeout)
    message_id = uuid.uuid4().hex
    try:
        ws.send(json.dumps({"message_id": message_id, "command": command, "args": kwargs}))
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(f"Matter Server command '{command}' timed out.")
            ws.settimeout(max(1.0, remaining))
            data = _recv_json(ws)
            if data.get("message_id") != message_id:
                continue
            if "result" in data:
                return data["result"]
            if "error_code" in data:
                details = data.get("details") or f"error_code={data['error_code']}"
                raise RuntimeError(f"Matter Server command '{command}' failed: {details}")
            raise RuntimeError(f"Unexpected Matter Server response for '{command}': {data}")
    finally:
        try:
            ws.close()
        except Exception:
            pass


def _validate_connection(ws_url: str, api_token: str) -> Dict[str, Any]:
    ws, server_info = _connect_socket(ws_url, api_token, DEFAULT_TIMEOUT)
    try:
        return server_info
    finally:
        try:
            ws.close()
        except Exception:
            pass


def _parse_attribute_path(attribute_path: str) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    endpoint_str, cluster_str, attribute_str = attribute_path.split("/")
    endpoint_id = int(endpoint_str) if endpoint_str.isdigit() else None
    cluster_id = int(cluster_str) if cluster_str.isdigit() else None
    attribute_id = int(attribute_str) if attribute_str.isdigit() else None
    return endpoint_id, cluster_id, attribute_id


def _attribute_path(endpoint_id: int, cluster_id: int, attribute_id: int) -> str:
    return f"{endpoint_id}/{cluster_id}/{attribute_id}"


def _group_node_attributes(node: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    endpoints: Dict[int, Dict[str, Any]] = {}
    attributes = node.get("attributes") or {}
    if not isinstance(attributes, dict):
        return endpoints

    for path, value in attributes.items():
        try:
            endpoint_id, _cluster_id, _attribute_id = _parse_attribute_path(str(path))
        except ValueError:
            continue
        if endpoint_id is None:
            continue
        endpoints.setdefault(endpoint_id, {})[str(path)] = value
    return endpoints


def _get_node_attribute(node: Dict[str, Any], endpoint_id: int, cluster_id: int, attribute_id: int) -> Any:
    attributes = node.get("attributes") or {}
    if not isinstance(attributes, dict):
        return None
    return attributes.get(_attribute_path(endpoint_id, cluster_id, attribute_id))


def _extract_device_type_ids(node: Dict[str, Any], endpoint_id: int) -> List[int]:
    raw = _get_node_attribute(node, endpoint_id, DESCRIPTOR_CLUSTER_ID, 0)
    if not isinstance(raw, list):
        return []

    device_type_ids: List[int] = []
    for item in raw:
        if isinstance(item, dict) and "deviceType" in item:
            try:
                device_type_ids.append(int(item["deviceType"]))
            except (TypeError, ValueError):
                continue
    return device_type_ids


def _select_model_for_endpoint(device_type_ids: List[int]) -> Optional[str]:
    for device_type_id in device_type_ids:
        if device_type_id in SUPPORTED_DEVICE_TYPE_MODELS:
            return SUPPORTED_DEVICE_TYPE_MODELS[device_type_id]
    return None


def _node_label(node: Dict[str, Any]) -> str:
    for attribute_id in (5, 14, 3):
        value = _get_node_attribute(node, 0, BASIC_INFORMATION_CLUSTER_ID, attribute_id)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"Matter Node {node.get('node_id', '?')}"


def _device_name(node: Dict[str, Any], endpoint_id: int, model: str, multi_endpoint: bool) -> str:
    base_name = _node_label(node)
    type_name = SUPPORTED_DEVICE_TYPE_NAMES.get(model, model)
    if multi_endpoint:
        return f"{base_name} - {type_name} (Endpoint {endpoint_id})"
    return base_name


def _find_node_by_id(node_id: int) -> Dict[str, Any]:
    for node in get_nodes():
        if int(node.get("node_id", -1)) == int(node_id):
            return node
    raise RuntimeError(f"Matter node {node_id} was not found.")


def _parse_did(did: str) -> Tuple[int, int]:
    raw = str(did).strip()
    if ":" not in raw:
        raise ValueError("Matter device id must use the form 'node_id:endpoint_id'.")
    node_id_raw, endpoint_id_raw = raw.split(":", 1)
    try:
        return int(node_id_raw), int(endpoint_id_raw)
    except ValueError as exc:
        raise ValueError("Matter device id must use numeric node_id and endpoint_id.") from exc


def _bool_from_any(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def _submit_login(session: MatterLoginSession, ws_url: str, api_token: str, pairing_code: str) -> None:
    normalized_url = _normalize_ws_url(ws_url)
    _validate_connection(normalized_url, api_token)

    if pairing_code.strip():
        _rpc(
            "commission_with_code",
            override={"ws_url": normalized_url, "api_token": api_token},
            code=pairing_code.strip(),
            network_only=False,
        )

    _save_auth_file(
        MatterConfig(
            ws_url=normalized_url,
            api_token=(api_token or "").strip() or None,
            updated_at=_now_string(),
        )
    )
    session.status = "ok"
    session.message = "Matter Server connected successfully."
    session.last_error = ""


def _build_form_html(session: MatterLoginSession, notice: str = "", error: str = "") -> bytes:
    notice_block = f"<p style='color:#0a7f2e'>{html.escape(notice)}</p>" if notice else ""
    error_block = f"<p style='color:#c62828'>{html.escape(error)}</p>" if error else ""
    ws_url = html.escape(session.metadata.get("ws_url", ""), quote=True)
    api_token = html.escape(session.metadata.get("api_token", ""), quote=True)
    pairing_code = html.escape(session.metadata.get("pairing_code", ""), quote=True)
    body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EntroFlow Matter Connect</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #f6f7fb; color: #111827; }}
    .wrap {{ max-width: 820px; margin: 48px auto; padding: 0 20px; }}
    .card {{ background: white; border-radius: 18px; padding: 28px; box-shadow: 0 18px 50px rgba(15, 23, 42, 0.08); }}
    h1 {{ margin: 0 0 12px; font-size: 28px; }}
    p, li {{ line-height: 1.65; }}
    ol {{ padding-left: 20px; }}
    label {{ display: block; margin-top: 18px; font-weight: 600; }}
    input, textarea {{ width: 100%; box-sizing: border-box; margin-top: 8px; padding: 12px 14px; border: 1px solid #d0d7e2; border-radius: 12px; font: inherit; }}
    textarea {{ min-height: 72px; resize: vertical; }}
    button {{ margin-top: 20px; background: #111827; color: white; border: 0; border-radius: 12px; padding: 12px 18px; font: inherit; cursor: pointer; }}
    code {{ background: #eef2ff; padding: 2px 6px; border-radius: 6px; }}
    .muted {{ color: #667085; font-size: 14px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Connect Matter</h1>
      <p>EntroFlow talks to Matter through an existing Matter Server runtime.</p>
      <ol>
        <li>Provide the Matter Server WebSocket URL.</li>
        <li>If your server requires auth, paste a bearer token.</li>
        <li>Optionally paste a QR code string or manual pairing code to commission one new device now.</li>
      </ol>
      <p class="muted">Examples: <code>ws://homeassistant.local:5580/ws</code>, <code>ws://192.168.1.20:5580/ws</code>, or <code>wss://matter.example.com/ws</code>.</p>
      {notice_block}
      {error_block}
      <form method="post" action="/submit">
        <input type="hidden" name="session_id" value="{html.escape(session.session_id, quote=True)}">
        <label for="ws_url">Matter Server WebSocket URL</label>
        <input id="ws_url" name="ws_url" type="text" value="{ws_url}" placeholder="ws://homeassistant.local:5580/ws" required>
        <label for="api_token">Bearer token (optional)</label>
        <textarea id="api_token" name="api_token" placeholder="Leave empty if the Matter Server does not require auth">{api_token}</textarea>
        <label for="pairing_code">QR code or manual pairing code (optional)</label>
        <textarea id="pairing_code" name="pairing_code" placeholder="Leave empty if you only want to save the Matter Server connection">{pairing_code}</textarea>
        <button type="submit">Save and Connect</button>
      </form>
    </div>
  </div>
</body>
</html>
"""
    return body.encode("utf-8")


def _build_success_html(message: str) -> bytes:
    body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>EntroFlow Matter Connected</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #f6f7fb; color: #111827; }}
    .wrap {{ max-width: 680px; margin: 48px auto; padding: 0 20px; }}
    .card {{ background: white; border-radius: 18px; padding: 28px; box-shadow: 0 18px 50px rgba(15, 23, 42, 0.08); }}
    h1 {{ margin: 0 0 12px; font-size: 28px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Matter connected</h1>
      <p>{html.escape(message)}</p>
      <p>You can close this window and return to the terminal.</p>
    </div>
  </div>
</body>
</html>
"""
    return body.encode("utf-8")


class _MatterConnectHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        session = self.server.session  # type: ignore[attr-defined]
        if self.path not in {"/", ""}:
            self.send_error(404)
            return

        body = _build_form_html(session, notice=session.message, error=session.last_error)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802
        session = self.server.session  # type: ignore[attr-defined]
        if self.path != "/submit":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length).decode("utf-8")
        form = parse_qs(raw_body)

        session.metadata["ws_url"] = form.get("ws_url", [""])[0].strip()
        session.metadata["api_token"] = form.get("api_token", [""])[0].strip()
        session.metadata["pairing_code"] = form.get("pairing_code", [""])[0].strip()
        session.submitted_at = time.time()

        try:
            _submit_login(
                session,
                session.metadata["ws_url"],
                session.metadata["api_token"],
                session.metadata["pairing_code"],
            )
            body = _build_success_html(session.message or "Matter Server connected successfully.")
        except Exception as exc:
            session.status = "error"
            session.message = ""
            session.last_error = str(exc)
            body = _build_form_html(session, error=session.last_error)

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        del format, args


def _create_login_session(timeout: int = 900) -> MatterLoginSession:
    session_id = uuid.uuid4().hex
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MatterConnectHandler)
    form_url = f"http://127.0.0.1:{server.server_address[1]}/"
    session = MatterLoginSession(
        session_id=session_id,
        form_url=form_url,
        timeout=timeout,
        created_at=time.time(),
        server=server,
        server_thread=threading.Thread(target=server.serve_forever, daemon=True),
    )
    server.session = session  # type: ignore[attr-defined]
    session.server_thread.start()
    return session


def start_qr_login(region: str = "cn") -> Dict[str, Any]:
    del region
    session = _create_login_session()
    with LOGIN_SESSIONS_LOCK:
        LOGIN_SESSIONS[session.session_id] = session
    return {
        "type": "form",
        "session_id": session.session_id,
        "qr_url": session.form_url,
        "expires_in": session.timeout,
        "message": "Open the local page to save the Matter Server WebSocket URL and optionally commission one new Matter device.",
    }


def poll_qr_login(session_id: str) -> Dict[str, Any]:
    with LOGIN_SESSIONS_LOCK:
        session = LOGIN_SESSIONS.get(session_id)

    if not session:
        return {"status": "error", "message": f"Unknown session_id '{session_id}'."}

    if time.time() - session.created_at > session.timeout:
        session.status = "expired"
        session.message = "The local Matter connection page expired."

    if session.status == "waiting":
        return {"status": "waiting", "message": "Still waiting for the local Matter connection form to be submitted."}
    if session.status == "ok":
        return {"status": "ok", "message": session.message or "Matter connected successfully."}
    if session.status == "expired":
        return {"status": "expired", "message": session.message or "Matter connection session expired."}
    return {"status": "error", "message": session.last_error or "Matter connection failed."}


def get_nodes() -> List[Dict[str, Any]]:
    result = _rpc("get_nodes")
    if not isinstance(result, list):
        raise RuntimeError("Matter Server returned an invalid node list.")
    return result


def get_device_descriptor(did: str) -> Dict[str, Any]:
    node_id, endpoint_id = _parse_did(did)
    node = _find_node_by_id(node_id)
    device_type_ids = _extract_device_type_ids(node, endpoint_id)
    model = _select_model_for_endpoint(device_type_ids)
    if not model:
        raise RuntimeError(f"Matter endpoint {did} is not mapped to a supported EntroFlow model.")

    return {
        "did": did,
        "node_id": node_id,
        "endpoint_id": endpoint_id,
        "model": model,
        "name": _device_name(node, endpoint_id, model, False),
        "node_label": _node_label(node),
        "product_name": _get_node_attribute(node, 0, BASIC_INFORMATION_CLUSTER_ID, 3),
        "vendor_name": _get_node_attribute(node, 0, BASIC_INFORMATION_CLUSTER_ID, 1),
        "available": bool(node.get("available", False)),
        "device_type_ids": device_type_ids,
    }


def read_device_attribute(did: str, cluster_id: int, attribute_id: int) -> Any:
    node_id, endpoint_id = _parse_did(did)
    path = _attribute_path(endpoint_id, cluster_id, attribute_id)
    result = _rpc("read_attribute", node_id=node_id, attribute_path=path)
    if isinstance(result, dict):
        return result.get(path)
    return result


def read_device_attributes(did: str, attributes: List[Tuple[int, int]]) -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    for cluster_id, attribute_id in attributes:
        values[_attribute_path(_parse_did(did)[1], cluster_id, attribute_id)] = read_device_attribute(did, cluster_id, attribute_id)
    return values


def write_device_attribute(did: str, cluster_id: int, attribute_id: int, value: Any) -> Any:
    node_id, endpoint_id = _parse_did(did)
    path = _attribute_path(endpoint_id, cluster_id, attribute_id)
    return _rpc("write_attribute", node_id=node_id, attribute_path=path, value=value)


def invoke_device_command(
    did: str,
    cluster_id: int,
    command_name: str,
    payload: Optional[Dict[str, Any]] = None,
    timed_request_timeout_ms: Optional[int] = None,
    interaction_timeout_ms: Optional[int] = None,
) -> Any:
    node_id, endpoint_id = _parse_did(did)
    kwargs: Dict[str, Any] = {
        "node_id": node_id,
        "endpoint_id": endpoint_id,
        "cluster_id": cluster_id,
        "command_name": command_name,
        "payload": payload or {},
    }
    if timed_request_timeout_ms is not None:
        kwargs["timed_request_timeout_ms"] = timed_request_timeout_ms
    if interaction_timeout_ms is not None:
        kwargs["interaction_timeout_ms"] = interaction_timeout_ms
    return _rpc("device_command", **kwargs)


def list_devices() -> List[Dict[str, Any]]:
    devices: List[Dict[str, Any]] = []
    for node in get_nodes():
        endpoint_attrs = _group_node_attributes(node)
        supported_endpoints: List[Tuple[int, str, List[int]]] = []
        for endpoint_id in sorted(endpoint_attrs):
            if endpoint_id == 0:
                continue
            device_type_ids = _extract_device_type_ids(node, endpoint_id)
            model = _select_model_for_endpoint(device_type_ids)
            if not model:
                continue
            supported_endpoints.append((endpoint_id, model, device_type_ids))

        multi_endpoint = len(supported_endpoints) > 1
        for endpoint_id, model, device_type_ids in supported_endpoints:
            devices.append(
                {
                    "did": f"{int(node.get('node_id', 0))}:{endpoint_id}",
                    "name": _device_name(node, endpoint_id, model, multi_endpoint),
                    "model": model,
                    "available": bool(node.get("available", False)),
                    "device_type_ids": device_type_ids,
                }
            )

    return devices
