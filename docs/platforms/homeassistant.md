# Home Assistant Platform Guide

## Before connecting

Read this platform guide before running `entroflow connect homeassistant`.

Home Assistant uses connector-managed token authentication. EntroFlow does not use a web login page for this platform.

## Requirements

- A reachable Home Assistant base URL, for example `http://homeassistant.local:8123`.
- A Home Assistant long-lived access token.

To create the token in Home Assistant, open your user profile, find Long-Lived Access Tokens, create a token for EntroFlow, and keep it private.

## Connect

```bash
entroflow connect homeassistant --url <home-assistant-url> --token <long-lived-access-token>
```

Example:

```bash
entroflow connect homeassistant --url http://homeassistant.local:8123 --token eyJ0eXAiOiJKV1Qi...
```

The Home Assistant connector validates the token and stores the credential locally in EntroFlow runtime storage.

## Control boundary

The Home Assistant token is for EntroFlow connector-managed connection, discovery, and setup. Agents must not use the token to call Home Assistant REST/WebSocket APIs directly for device control.

After connecting, Home Assistant devices can appear in discovery before they are registered in EntroFlow runtime. Discovery is not control permission. Before controlling any HA device, set up the exact EntroFlow physical/logical device with `entroflow setup ...`, then use `device_search(...)` to inspect the registered EntroFlow device id and `supported_actions`.

MCP is runtime-only by default. Use MCP setup tools only in Docker/OpenClaw sidecar mode with `ENTROFLOW_MCP_MODE=all`, where the agent container may not have the local CLI. In sidecar setup, confirm the platform with `platform_select_prepare(...)`, list candidates with `platform_devices(...)`, prepare registration with `device_setup_prepare(...)`, and register with `device_setup(...)` only after the user confirms the summary.

If the user asks to control a HA device that is not registered yet, stop and ask to set up the exact discovered physical/logical device first. Do not choose a different HA entity or call HA services directly.

Home Assistant entity names are not EntroFlow aliases. If the user says a room name, "main light", "switch", or another household nickname, do not guess from HA entity names or domains. Show the full discovered device list or a numbered/pageable full list and ask the user to select the exact discovered device. If none of the shown devices is correct, ask the user to provide the exact device/entity instead of choosing a likely candidate.

Many Home Assistant integrations expose multiple entities for one physical device. EntroFlow setup is per physical/logical device, not per entity. For example, a Xiaomi three-gang switch should be registered as one switch device, with left/middle/right handled as action arguments or aliases in `remark`; an air purifier may have fan, sensor, switch, and button entities grouped under one EntroFlow device.

Supported status is not identity. Do not treat "the only supported light" as the user's target. After the user selects the exact device, store the user's nickname in the EntroFlow `name` or `remark` during setup. Future control should use that registered EntroFlow alias.

## Verify

```bash
entroflow list-devices --platform homeassistant
```

If the command cannot reach Home Assistant, check that the URL is reachable from the machine running the agent and that the token is still valid.
