# Matter Platform Guide

Use this guide when the user wants to connect EntroFlow directly to a Matter fabric.

## Platform Identity

- platform id: `matter`
- common aliases: `matter`, `matter server`

Always use the platform id `matter` in CLI commands.

## When To Use This Platform

Choose `matter` when the user already has a Matter controller stack and wants EntroFlow to talk to Matter devices through that runtime directly, instead of going through a vendor cloud.

Examples:

- a local `python-matter-server` deployment
- the Home Assistant Matter Server add-on
- a self-hosted Matter controller exposed over WebSocket

## Connection Flow

Run:

```bash
entroflow connect matter
```

The CLI opens a local browser page served by EntroFlow.

On that page, provide:

- the Matter Server WebSocket URL
- an optional bearer token if the server is protected
- an optional QR code or manual pairing code if you want to commission a new device during setup

Common WebSocket URL examples:

```text
ws://homeassistant.local:5580/ws
ws://192.168.1.20:5580/ws
wss://matter.example.com/ws
```

## After Connection

List the Matter devices that already exist on the connected fabric:

```bash
entroflow list-devices --platform matter
```

If the user only wants the resource files locally, download the exact device resource version:

```bash
entroflow download --platform matter --model <model> --version <version>
```

If the user wants the device to become usable through MCP, ask the user to confirm:

- `name`
- `location`
- `remark`

Then run:

```bash
entroflow setup --platform matter --did <did> --model <model> --version <version> --name "<name>" --location "<location>" --remark "<remark>"
```

## Notes

- EntroFlow currently models Matter through reusable standard device types, not per-brand model packs.
- A single physical Matter node can expose multiple usable endpoints. The discovered `did` is therefore `node_id:endpoint_id`.
- The platform connector intentionally keeps the setup surface small and expects the Matter controller stack to handle the full fabric lifecycle.
- This Matter integration has not been verified yet with real retail Matter devices. If you test it in the field, feedback about working models, failing models, and edge cases is very welcome.
- If the local guide or behavior looks outdated, run:

```bash
entroflow update
```
