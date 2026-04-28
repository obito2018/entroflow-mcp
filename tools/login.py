# -*- coding: utf-8 -*-
import threading
import time
from typing import Dict

from core import loader

_login_results: Dict[str, Dict[str, str]] = {}
_login_threads: Dict[str, threading.Thread] = {}


def _poll_login_background(platform: str, session_id: str):
    connector = loader.load_connector(platform)
    for _ in range(100):  # up to about 5 minutes
        try:
            result = connector.poll_qr_login(session_id)
        except Exception as exc:
            _login_results[session_id] = {"status": "error", "message": str(exc)}
            return
        status = result.get("status", "")
        if status == "ok":
            _login_results[session_id] = {"status": "ok", "message": "Login succeeded."}
            return
        if status == "expired":
            _login_results[session_id] = {"status": "expired", "message": "Login QR code expired."}
            return
        time.sleep(3)
    _login_results[session_id] = {"status": "timeout", "message": "Login polling timed out."}


def login_start(platform: str, login_option: str = "local-page") -> str:
    """Start platform login and return the login surface details."""
    try:
        connector = loader.load_connector(platform)
        try:
            result = connector.start_qr_login(region="cn", login_option=login_option)
        except TypeError:
            result = connector.start_qr_login(region="cn")
        session_id = result["session_id"]
        _login_results.pop(session_id, None)
        t = threading.Thread(
            target=_poll_login_background,
            args=(platform, session_id),
            daemon=True,
        )
        _login_threads[session_id] = t
        t.start()

        lines = [
            "type=qrcode",
            f"qr_url={result['qr_url']}",
            f"login_option={result.get('login_option', login_option)}",
        ]
        qr_file_path = str(result.get("qr_file_path") or "").strip()
        if qr_file_path:
            lines.append(f"qr_file_path={qr_file_path}")
        lines.extend(
            [
                f"session_id={session_id}",
                f"expires_in={result['expires_in']}",
                f"message={result.get('message', 'Open qr_url and complete login in the Mi Home app.')}",
                f"next=After scanning, call login_poll(platform='{platform}', session_id='{session_id}')",
            ]
        )
        return "\n".join(lines)
    except Exception as exc:
        return f"Login start failed: {exc}"


def login_poll(platform: str, session_id: str) -> str:
    """Check background login state. Returns ok / waiting / expired / error."""
    if not session_id:
        return "Missing session_id. Pass the session_id returned by login_start()."
    for _ in range(20):
        if session_id in _login_results:
            result = _login_results.pop(session_id)
            _login_threads.pop(session_id, None)
            status = result["status"]
            if status == "ok":
                return (
                    "status=ok\n"
                    f"message=Login succeeded. You can now continue device discovery for platform '{platform}'."
                )
            if status == "expired":
                return (
                    "status=expired\n"
                    f"message=Login QR code expired. Run login_start(platform='{platform}') again."
                )
            return f"status={status}\nmessage={result['message']}"
        time.sleep(3)
    return (
        "status=waiting\n"
        f"message=User has not completed login yet. Call login_poll(platform='{platform}', session_id='{session_id}') again later."
    )
