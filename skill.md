---
name: entroflow
description: Use when an agent needs to connect platforms and set up EntroFlow devices through the local CLI before using the runtime MCP tools for device_search, device_status, and device_control.
short-description: Connect and set up EntroFlow devices
---

# EntroFlow Skill Guide

EntroFlow connects an agent to physical devices.

This integration is split into two layers:

- Low-frequency setup uses the local `entroflow` CLI.
- High-frequency runtime control uses the MCP tools.

## When To Use CLI

Use CLI for any one-time or low-frequency operation:

- listing currently supported platforms
- connecting a platform
- authenticating an account
- listing connected devices
- downloading a device resource package
- setting up a device into the local runtime
- updating local assets or the server

### CLI Commands

List currently supported platforms:

```bash
entroflow list-platforms
entroflow list-platforms mi
```

Before connecting a platform, read the matching local platform guide at:

```text
~/.entroflow/docs/platforms/<platform>.md
```

`entroflow connect <platform>` syncs the latest published platform guide before login starts.
It also refreshes the local platform device support table.

If you want to refresh guides in advance for already connected platforms, run:

```bash
entroflow update
```

If the guide is still missing after `entroflow connect` or `entroflow update`, tell the user the platform-specific guide has not been published yet and continue only if they still want to proceed.

Connect a platform:

```bash
entroflow connect <platform>
```

Before running `entroflow connect <platform>`, read `~/.entroflow/docs/platforms/<platform>.md` first.
Each platform has its own login method. Follow the platform guide instead of guessing the login flow from the skill file.

List devices from connected platforms:

```bash
entroflow list-devices
```

Download a device resource package into local assets:

```bash
entroflow download --platform mihome --model yeelink.light.lamp22 --version 1.0.0
```

Use `download` when the user only wants the resource files locally.
It does not instantiate or register the device.

Set up a device into the local runtime:

```bash
entroflow setup --platform mihome --did 708678806 --model yeelink.light.lamp22 --version 1.0.0 --name "Desk Lamp" --location "Office" --remark "Display light"
```

Use `setup` when the device should become directly usable through the runtime MCP tools.

Update local assets and server code:

```bash
entroflow update
```

`entroflow update` refreshes platform guides and platform device support tables for locally installed connectors, even if the platform package version did not change.

## When To Use MCP

Use MCP only after setup is complete.

The runtime MCP surface is intentionally minimal:

1. `device_search(query)`
2. `device_status(device_id)`
3. `device_control(device_id, action)`

## Required Setup Flow

For a brand new user or a new platform, always follow this order:

1. Run `entroflow list-platforms [query]`.
2. Identify the exact platform id.
3. Read `~/.entroflow/docs/platforms/<platform>.md` if it was synced locally.
4. Run `entroflow connect <platform>`.
5. If the guide is not available after connect, tell the user the platform-specific guide has not been published yet.
6. Run `entroflow list-devices`.
7. Ask the user which exact device should be set up.
8. Ask the user to confirm:
   - `name`
   - `location`
   - `remark`
9. Run `entroflow setup ...`.
10. Before the first runtime control of a specific device, run `device_search("<device_id>")` and inspect `supported_actions`.
11. After confirming the supported action names, switch to MCP runtime tools.

## Important Rules

1. Do not use MCP for installation, login, discovery, or updates.
2. Do not invent `name`, `location`, or `remark`. Ask the user.
3. Do not assume a platform id. Always confirm it with `entroflow list-platforms`.
4. Before `entroflow connect <platform>`, read `~/.entroflow/docs/platforms/<platform>.md`.
5. `entroflow connect <platform>` will sync the latest published platform guide automatically when one exists.
6. If the guide is still missing after `connect` or `update`, tell the user the platform guide is not published yet and ask whether they want to continue without it.
7. If the user only needs the resource package, use `entroflow download`.
8. If the user wants the device to become callable through MCP, use `entroflow setup`.
9. `entroflow connect <platform>` and `entroflow update` both refresh the local platform device support table.
10. Before the first control of any specific device, you must inspect `supported_actions` via `device_search(...)`.
11. Action names are device-specific by default. Do not assume generic names such as `set_power`.
12. If runtime tools say a device is missing, go back to the CLI setup flow.
13. If the user wants to add another device on an already connected platform, use:
   - `entroflow list-devices`
   - `entroflow setup ...`

## Runtime Patterns

Find devices:

```text
device_search("lamp")
device_search("all")
device_search("mihome:709145591")
```

Read status:

```text
device_status("mihome:708678806")
```

Control a device:

```text
device_control("mihome:709145591", {"action": "turn_off", "args": {}})
```

Before control, run `device_search(...)` and inspect `supported_actions`.
Action names are device-specific by default. Do not assume generic names such as `set_power`.

## Failure Recovery

- If `entroflow connect` fails, re-run the same command and complete login again.
- If `entroflow setup` fails because the model is unsupported, stop and tell the user the device is not supported yet.
- If `device_control` fails because the runtime is missing, the device was not set up correctly. Go back to the CLI flow.
