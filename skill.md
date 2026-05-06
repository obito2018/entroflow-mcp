---
name: entroflow
description: Use when an agent needs to connect platforms, set up EntroFlow devices, and control devices through MCP tools.
short-description: Connect and control EntroFlow devices
---

# EntroFlow Skill Guide

EntroFlow connects an agent to physical devices.

Use the local `entroflow` CLI when it is available. In Docker sidecar mode, the agent container may not have the CLI; then use the EntroFlow MCP setup tools instead.

EntroFlow is the control boundary. Platform connectors and platform credentials are for connection, discovery, and setup. Do not control devices through platform-native APIs such as Home Assistant REST/WebSocket APIs, even if credentials are available. A device must be set up into EntroFlow runtime before control.

Do not guess which physical device the user means from a vague phrase such as "main light", "bedroom light", or "the switch". Use only registered EntroFlow `name`, `location`, and `remark` as aliases for control. If no registered device matches the phrase exactly enough, ask the user to choose the exact device id or set up a device with that alias first.

## Setup Flow

For a new user, platform, or device:

1. List supported platforms with `entroflow list-platforms [query]` or MCP `platform_list(query)`.
2. Confirm the exact platform id.
3. Before connecting, read the platform guide if available at `~/.entroflow/docs/platforms/<platform>.md`.
4. Connect with `entroflow connect <platform>` or MCP `platform_connect(platform, ...)`.
5. If MCP `platform_connect` returns a pending `session_id` with a `scan_qr` action, send the QR image directly to the user. In OpenClaw, use the Message tool with `action='send'`, `target=<current chat target>`, and `media=<public_url>`; never omit `target`. If the Message tool is unavailable, send `markdown_image` or `public_url`. If neither is present, call `platform_connect_qr(platform, session_id)` and show the returned Markdown/image result to the user. Then call `platform_connect_poll(platform, session_id)` after the user scans/confirms.
6. List discovered devices with `entroflow list-devices --platform <platform>` or MCP `platform_devices(platform)`.
7. Ask the user which exact device to set up.
8. Ask the user to confirm `name`, `location`, and `remark`; do not invent these values. Put user-facing aliases such as "main light" in `name` or `remark` during setup.
9. Set up the device with `entroflow setup ...` or MCP `device_setup(...)`.
10. Before the first control of a specific device, run `device_search("<device_id>")` and inspect `supported_actions`.
11. Control the device only with an action name shown in `supported_actions`.

If a device appears in `list-devices` / `platform_devices` but is not set up, stop and ask whether to set it up. Do not control a discovered-but-unregistered platform entity directly.

When the user's phrase does not clearly match a registered EntroFlow alias, list all discovered devices from `platform_devices(platform)` or provide a numbered/pageable full list, then ask the user to choose the exact `device_id`. Do not narrow the list to devices you think are likely. Do not say "only" or "unique" based on supported status, model type, entity domain, room guess, or device name guess.

You may say which devices are supported or unsupported, but support status is not identity. A supported floor lamp is not the user's "main light" unless the user explicitly selected it or registered that alias.

## CLI Commands

```bash
entroflow list-platforms
entroflow connect <platform>
entroflow list-devices --platform <platform>
entroflow setup --platform <platform> --did <did> --model <model> --version <version> --name "<name>" --location "<location>" --remark "<remark>"
entroflow update
entroflow uninstall
```

`entroflow connect <platform>` and `entroflow update` refresh platform guides and platform device support tables.

Use `entroflow uninstall` only when the user explicitly wants to remove EntroFlow. Use `--keep-data` if they want to keep local device data and downloaded assets.

## MCP Tools

Setup tools, mainly for Docker sidecar mode:

```text
platform_list(query)
platform_connect(platform, url, token, inputs, presentation, timeout)
platform_connect_qr(platform, session_id)
platform_connect_poll(platform, session_id, url, token, inputs, presentation, timeout)
platform_devices(platform)
device_setup(platform, did, model, name, location, remark, version)
entroflow_update()
```

MCP `platform_connect` is non-blocking. It starts the platform-specific connection flow and returns `status`, optional `session_id`, and connector-defined actions. Do not wait inside the same tool call for the user to scan or confirm.

For a `scan_qr` action, prefer the agent's native image-send tool. In OpenClaw, use the Message tool with `action='send'`, `target=<current chat target>`, `media=<public_url>`, and a short message asking the user to scan. The `target` must come from the current chat/message context; do not call Message without it. If native image sending is unavailable, send the returned `markdown_image`; if Markdown image rendering fails, send `public_url`. It is a short-lived HTTPS fallback that works for Docker, remote chat, and headless agents. If neither is present, use `platform_connect_qr(platform, session_id)` and show its Markdown/image result. Do not try to send the returned local file path as a chat attachment; some agents restrict attachment paths. After the user scans and confirms, call `platform_connect_poll` with the same `session_id`.

Runtime tools:

```text
device_search(query)
device_status(device_id)
device_control(device_id, action)
```

Before `device_control`, always run `device_search` for that device and inspect `supported_actions`. Action names and argument names are device-specific by default; do not assume generic names such as `set_power`.

`device_control` has two top-level tool parameters, but the second `action` parameter can carry action args:

```text
device_control("homeassistant:<device_id>", {"action": "turn_on", "args": {"channels": "middle"}})
```

Use the exact action name and arg names shown by `supported_actions`. If a driver needs `channel`, `channels`, `value`, `brightness`, `temperature`, or another action parameter, put it inside `action.args`; do not conclude that `device_control` cannot pass parameters and do not use platform-native APIs as a workaround.

Never use a platform-native API as a shortcut for runtime control. For Home Assistant, do not call HA services directly to turn lights, switches, covers, or other entities on/off. Use `device_setup` first, then `device_control` on the registered EntroFlow device id.

If `device_search("main light")` does not return a registered EntroFlow runtime device whose `name`, `location`, or `remark` clearly contains that alias, ask for clarification. Do not infer the target from platform device names, model names, domains, or entity categories.

## Recovery

- If connection fails, read the connector message and platform guide, fix the missing input or local environment, then retry the same platform command/tool.
- If setup fails because the model is unsupported, stop and tell the user the device is not supported yet.
- If runtime tools say a device is missing, go back to the setup flow.
