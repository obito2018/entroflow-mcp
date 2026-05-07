# OpenClaw Docker Sidecar

This document describes the EntroFlow setup path for Docker/OpenClaw sidecar deployments.

## Tool Boundary

Default EntroFlow MCP is runtime-only:

```text
ENTROFLOW_MCP_MODE=runtime
```

Runtime mode exposes only:

```text
device_search
device_status
device_control
```

Use the local `entroflow` CLI for platform connection, discovery, setup, update, and uninstall whenever the CLI is available.

Docker/OpenClaw sidecar is different: the agent container may not have the host CLI, host file paths, or localhost browser access. The sidecar image therefore runs with:

```text
ENTROFLOW_MCP_MODE=all
```

This exposes both runtime tools and setup tools through MCP.

## Sidecar Setup Tools

The setup tools are:

```text
platform_list(query)
platform_connect(platform, url, token, inputs, presentation, timeout)
platform_connect_qr(platform, session_id)
platform_connect_poll(platform, session_id, url, token, inputs, presentation, timeout)
platform_select_prepare(platform, evidence)
platform_devices(platform, supported_only, platform_confirmation_token)
device_setup_prepare(platform, did, model, name, location, remark, version, platform_confirmation_token)
device_setup(platform, did, model, name, location, remark, version, confirmation_token)
entroflow_update()
```

## Platform Selection

Do not silently reuse the previous platform for a new or unregistered device.

When the user explicitly names a platform in the current task, call:

```text
platform_select_prepare(platform, evidence="user_mentioned_platform")
```

When the platform was just connected in the same task, call:

```text
platform_select_prepare(platform, evidence="just_connected_platform")
```

When exactly one platform is connected and the user did not name a platform, the agent may use:

```text
platform_select_prepare(platform, evidence="single_connected_platform")
```

and should tell the user it is searching that single connected platform.

If none of those evidence values applies, call `platform_select_prepare(platform)` without evidence and ask the user whether the new device is on that platform or another platform. Use the returned `platform_confirmation_token` only after the user confirms.

The same `platform_confirmation_token` must be passed to `platform_devices` and `device_setup_prepare`.

## Device Setup Confirmation

Device setup is a write operation. Do not infer or invent registration metadata.

After the user chooses the exact physical/logical device and provides `name`, `location`, and `remark`, call:

```text
device_setup_prepare(..., platform_confirmation_token=<token>)
```

Show the returned registration summary to the user and wait for explicit confirmation. Only then call:

```text
device_setup(..., confirmation_token=<token>)
```

## QR Login

Sidecar and remote chat environments cannot rely on localhost or local file paths. For a `scan_qr` action:

1. Prefer the agent's native image-send tool.
2. In OpenClaw, use the Message tool with `action="send"`, `target=<current chat target>`, `media=<public_url>`, and a short scan instruction.
3. Do not omit `target`.
4. If native image sending is unavailable, send `markdown_image` or `public_url`.
5. If neither is available, call `platform_connect_qr(platform, session_id)` and show the returned image result.
6. Do not send local file paths as chat attachments.

After the user scans and confirms, call `platform_connect_poll(platform, session_id)`.

## Runtime Control

After setup, switch back to runtime behavior:

1. `device_search(query)`
2. Inspect `supported_actions`
3. `device_status(device_id)` when needed
4. `device_control(device_id, action)`

Never call platform-native APIs such as Home Assistant services directly for runtime control.
