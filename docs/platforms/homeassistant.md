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

After connecting, a Home Assistant entity can appear in discovery before it is registered in EntroFlow runtime. Discovery is not control permission. Before controlling any HA device, set up the exact entity with `entroflow setup ...` or MCP `device_setup(...)`, then use `device_search(...)` to inspect the registered EntroFlow device id and `supported_actions`.

If the user asks to control a HA device that is not registered yet, stop and ask to set up the exact discovered entity first. Do not choose a different HA entity or call HA services directly.

Home Assistant entity names are not EntroFlow aliases. If the user says a room name, "main light", "switch", or another household nickname, do not guess from HA entity names or domains. Show the full discovered device list or a numbered/pageable full list and ask the user to select the exact discovered entity. If none of the shown devices is correct, ask the user to provide the exact entity/device instead of choosing a likely candidate.

Supported status is not identity. Do not treat "the only supported light" as the user's target. After the user selects the exact entity, store the user's nickname in the EntroFlow `name` or `remark` during setup. Future control should use that registered EntroFlow alias.

## Verify

```bash
entroflow list-devices --platform homeassistant
```

If the command cannot reach Home Assistant, check that the URL is reachable from the machine running the agent and that the token is still valid.
