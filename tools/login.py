# -*- coding: utf-8 -*-
import threading
import time
from typing import Dict

from core import loader

_login_results: Dict[str, Dict[str, str]] = {}
_login_threads: Dict[str, threading.Thread] = {}


def _poll_login_background(platform: str, session_id: str):
    connector = loader.load_connector(platform)
    for _ in range(100):  # 最多轮询约 5 分钟
        try:
            result = connector.poll_qr_login(session_id)
        except Exception as e:
            _login_results[session_id] = {"status": "error", "message": str(e)}
            return
        status = result.get("status", "")
        if status == "ok":
            _login_results[session_id] = {"status": "ok", "message": "登录成功！"}
            return
        if status == "expired":
            _login_results[session_id] = {"status": "expired", "message": "二维码已过期。"}
            return
        time.sleep(3)
    _login_results[session_id] = {"status": "timeout", "message": "轮询超时。"}


def login_start(platform: str) -> str:
    """发起平台登录，返回登录方式和所需信息。后台立即开始轮询，用户操作期间保持连接。
    返回 type=qrcode 时展示二维码，type=form 时引导用户填写表单。"""
    try:
        connector = loader.load_connector(platform)
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
        return (
            f"type=qrcode\n"
            f"qr_url={result['qr_url']}\n"
            f"session_id={session_id}\n"
            f"expires_in={result['expires_in']}\n"
            f"message=请在浏览器中打开 qr_url，用米家 App 扫描二维码。\n"
            f"next=扫码后调用 login_poll(platform='{platform}', session_id='{session_id}')"
        )
    except Exception as e:
        return f"登录启动失败: {e}"


def login_poll(platform: str, session_id: str) -> str:
    """检查后台登录状态。返回 ok / waiting / expired / error。"""
    if not session_id:
        return "缺少 session_id，请传入 login_start 返回的 session_id。"
    for _ in range(20):
        if session_id in _login_results:
            result = _login_results.pop(session_id)
            _login_threads.pop(session_id, None)
            status = result["status"]
            if status == "ok":
                return f"status=ok\nmessage=登录成功！现在可以调用 device_discover(platform='{platform}') 发现设备。"
            if status == "expired":
                return f"status=expired\nmessage=二维码已过期，请重新调用 login_start(platform='{platform}')。"
            return f"status={status}\nmessage={result['message']}"
        time.sleep(3)
    return f"status=waiting\nmessage=用户尚未完成扫码，请稍后再次调用 login_poll(platform='{platform}', session_id='{session_id}')"
