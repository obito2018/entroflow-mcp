# Home Assistant Platform Guide

Use this guide when the user wants to connect a Home Assistant instance.

## Platform Identity

- platform id: `homeassistant`
- common aliases: `ha`, `hass`, `home assistant`

Always use the platform id `homeassistant` in CLI commands.

## When To Use This Platform

Choose `homeassistant` when the user already manages devices through a Home Assistant server and wants EntroFlow to use that existing integration layer.

Examples:

- Zigbee, Matter, or vendor devices already bridged into Home Assistant
- local dashboards or automations already running in Home Assistant
- devices that expose useful Home Assistant entities and services

## Connection Flow

Run:

```bash
entroflow connect homeassistant
```

The CLI opens a local browser page served by EntroFlow.

On that page, provide:

- the Home Assistant base URL
- a Home Assistant long-lived access token

You can create a long-lived access token from your Home Assistant profile page.

Common URL examples:

```text
http://homeassistant.local:8123
https://ha.example.com
```

## After Connection

List the available Home Assistant devices:

```bash
entroflow list-devices --platform homeassistant
```

If the user only wants the resource files locally, download the exact device resource version:

```bash
entroflow download --platform homeassistant --model <model> --version <version>
```

If the user wants the device to become usable through MCP, ask the user to confirm:

- `name`
- `location`
- `remark`

Then run:

```bash
entroflow setup --platform homeassistant --did <did> --model <model> --version <version> --name "<name>" --location "<location>" --remark "<remark>"
```

## Notes

- EntroFlow stores the Home Assistant URL and token locally after a successful connection.
- If the token is revoked or expires, run `entroflow connect homeassistant` again.
- Device discovery prefers Home Assistant registry data when available and falls back to raw entity listing if necessary.
- If the local guide or behavior looks outdated, run:

```bash
entroflow update
```
