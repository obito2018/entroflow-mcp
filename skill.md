---
name: entroflow
description: Use when an agent needs to connect platforms, set up EntroFlow devices, and control devices through MCP tools.
short-description: Connect and control EntroFlow devices
---

# EntroFlow Skill Guide

EntroFlow connects an agent to physical devices.

Use the local `entroflow` CLI when it is available. In Docker sidecar mode, the agent container may not have the CLI; then use the EntroFlow MCP setup tools instead.

## Setup Flow

For a new user, platform, or device:

1. List supported platforms with `entroflow list-platforms [query]` or MCP `platform_list(query)`.
2. Confirm the exact platform id.
3. Before connecting, read the platform guide if available at `~/.entroflow/docs/platforms/<platform>.md`.
4. Connect with `entroflow connect <platform>` or MCP `platform_connect(platform, ...)`.
5. List discovered devices with `entroflow list-devices --platform <platform>` or MCP `platform_devices(platform)`.
6. Ask the user which exact device to set up.
7. Ask the user to confirm `name`, `location`, and `remark`; do not invent these values.
8. Set up the device with `entroflow setup ...` or MCP `device_setup(...)`.
9. Before the first control of a specific device, run `device_search("<device_id>")` and inspect `supported_actions`.
10. Control the device only with an action name shown in `supported_actions`.

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
platform_devices(platform)
device_setup(platform, did, model, name, location, remark, version)
entroflow_update()
```

Runtime tools:

```text
device_search(query)
device_status(device_id)
device_control(device_id, action)
```

Before `device_control`, always run `device_search` for that device and inspect `supported_actions`. Action names are device-specific by default; do not assume generic names such as `set_power`.

## Recovery

- If connection fails, read the connector message and platform guide, fix the missing input or local environment, then retry the same platform command/tool.
- If setup fails because the model is unsupported, stop and tell the user the device is not supported yet.
- If runtime tools say a device is missing, go back to the setup flow.
