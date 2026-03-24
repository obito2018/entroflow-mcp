# -*- coding: utf-8 -*-
from core import loader, store


def device_search(query: str) -> str:
    """搜索已注册设备。传 'all' 返回全部，或传关键词匹配名称/型号/位置。"""
    devices = store.load()
    if not devices:
        return "没有已注册的设备。请先使用 platform_install 安装平台包并完成设备注册。"

    if query.lower() == "all":
        matched = devices
    else:
        q = query.lower()
        matched = [
            d for d in devices
            if q in d.get("name", "").lower()
            or q in d.get("model", "").lower()
            or q in d.get("location", "").lower()
            or q in d.get("device_id", "").lower()
        ]

    if not matched:
        return f"没有找到匹配 '{query}' 的设备。"

    lines = [f"找到 {len(matched)} 个设备：\n"]
    for i, d in enumerate(matched, 1):
        lines.append(f"[{i}] {d.get('name', '?')}")
        lines.append(f"    device_id : {d.get('device_id', '?')}")
        lines.append(f"    model     : {d.get('model', '?')}")
        lines.append(f"    platform  : {d.get('platform', '?')}")
        lines.append(f"    location  : {d.get('location', '?')}")
        lines.append(f"    remark    : {d.get('remark', '?')}")
        try:
            device_mod = loader.load_device_class(d["platform"], d["model"])
            specs = getattr(device_mod, "ACTION_SPECS", [])
            if specs:
                lines.append("    supported_actions:")
                for s in specs:
                    lines.append(
                        f"      - {s['action']}: {s['description']} "
                        f"(args: {s.get('args', 'None')}, range: {s.get('range', '-')})"
                    )
        except Exception:
            pass
        lines.append("")
    return "\n".join(lines)


def device_status(device_id: str) -> str:
    """查询设备当前状态，返回属性值（开关、音量、亮度、温度等）。只读操作。"""
    record = store.find(device_id)
    if not record:
        return f"设备 '{device_id}' 未找到。请先用 device_search 查看已注册设备。"
    try:
        device = loader.create_device_instance(record)
        result = device.query_status()
        return f"设备: {record.get('name', '?')} ({device_id})\n{result}"
    except Exception as e:
        return f"查询状态失败: {e}"


def device_control(device_id: str, actions: list) -> str:
    """对已注册设备执行控制指令。action 和可用参数见 device_search 返回的 supported_actions。"""
    record = store.find(device_id)
    if not record:
        return f"设备 '{device_id}' 未找到。请先用 device_search 查看已注册设备。"
    try:
        device = loader.create_device_instance(record)
    except Exception as e:
        return f"加载设备失败: {e}"

    lines = [f"设备: {record.get('name', '?')} ({device_id})", "结果:"]
    for entry in actions:
        action = entry.get("action", "")
        args = entry.get("args", {})
        if not action:
            lines.append("  (跳过: 缺少 action 名称)")
            continue
        result = device.perform_action(action, **args)
        lines.append(f"  {action}: {result}")
    return "\n".join(lines)


def device_register(did: str, model: str, platform: str,
                    name: str, location: str, remark: str) -> str:
    """将设备写入本地注册表。
    调用前必须先向用户确认以下三个字段，不得自行填写或使用占位值：
    - name: 设备昵称（如"客厅大电视"）
    - location: 设备所在位置（如"客厅"、"主卧"）
    - remark: 备注信息（如设备用途、外观特征等）
    did 和 model 从 device_discover 结果中获取，platform 从 platform_list 获取。"""
    if not all([did, model, platform, name, location, remark]):
        return "缺少必填字段。did、model、platform、name、location、remark 均为必填。"
    result = store.register(did, model, platform, name, location, remark)
    if result["ok"]:
        r = result["record"]
        return f"设备已注册: {r['name']} ({r['device_id']}) 位置: {r['location']}"
    return result["message"]
