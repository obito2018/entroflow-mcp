# -*- coding: utf-8 -*-
from core import loader, store


def device_search(query: str) -> str:
    """Search registered devices. Use 'all' to list everything and inspect supported_actions before control."""
    devices = store.load()
    if not devices:
        return (
            "No devices are registered yet. "
            "Connect a platform and run `entroflow setup ...` or MCP `device_setup(...)` before control. "
            "Do not bypass EntroFlow by controlling platform-native entities directly."
        )

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
        return (
            f"No registered EntroFlow runtime devices matched '{query}'. "
            "If the platform device was only discovered, run setup first. "
            "Do not control a platform-native entity directly."
        )

    lines = [f"Found {len(matched)} device(s):", ""]
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
    """Read the current status of a registered device."""
    record = store.find(device_id)
    if not record:
        return f"Device '{device_id}' was not found in EntroFlow runtime. Use device_search first, or set up the discovered platform device before control."
    try:
        device = loader.create_device_instance(record)
        result = device.query_status()
        return f"Device: {record.get('name', '?')} ({device_id})\n{result}"
    except Exception as e:
        return f"Failed to query device status: {e}"


def device_control(device_id: str, action) -> str:
    """Execute a runtime action on a registered device. Run device_search first to inspect supported_actions."""
    record = store.find(device_id)
    if not record:
        return f"Device '{device_id}' was not found in EntroFlow runtime. Do not control platform-native entities directly; set up the device first."
    try:
        device = loader.create_device_instance(record)
    except Exception as e:
        return f"Failed to load device runtime: {e}"

    action_list = action if isinstance(action, list) else [action]

    lines = [f"Device: {record.get('name', '?')} ({device_id})", "Result:"]
    for entry in action_list:
        if isinstance(entry, str):
            action_name = entry
            args = {}
        elif isinstance(entry, dict):
            action_name = entry.get("action", "")
            args = entry.get("args", {})
        else:
            lines.append(f"  (skipped: invalid action payload type {type(entry).__name__})")
            continue

        if not action_name:
            lines.append("  (skipped: missing action name)")
            continue
        if not isinstance(args, dict):
            lines.append(f"  {action_name}: skipped because args must be an object")
            continue

        result = device.perform_action(action_name, **args)
        lines.append(f"  {action_name}: {result}")
    return "\n".join(lines)


def device_register(
    did: str,
    model: str,
    platform: str,
    name: str,
    location: str,
    remark: str,
) -> str:
    """Register a device in the local runtime store."""
    if not all([did, model, platform, name, location, remark]):
        return "Missing required fields: did, model, platform, name, location, remark."
    result = store.register(did, model, platform, name, location, remark)
    if result["ok"]:
        record = result["record"]
        return f"Registered device: {record['name']} ({record['device_id']}) at {record['location']}"
    return result["message"]
