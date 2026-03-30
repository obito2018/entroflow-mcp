# Mi Home Platform Guide

Use this guide when the user wants to connect Xiaomi Mi Home / Mijia.

## Platform Identity

- platform id: `mihome`
- common aliases: `mijia`, `xiaomi`, `mi home`

Always use the platform id `mihome` in CLI commands.

## When To Use This Platform

Choose `mihome` when the user's account and devices are managed through the Mi Home app.

Examples:

- Xiaomi smart lights
- Xiaomi sensors
- Xiaomi home appliances that appear inside Mi Home

## Connection Flow

Run:

```bash
entroflow connect mihome
```

The CLI will try to open the login URL in the default browser automatically.
If the browser does not open, use the printed URL manually.

Complete the login confirmation in the Mi Home app, then continue the CLI flow until it reports success.

## After Connection

List the available Mi Home devices:

```bash
entroflow list-devices --platform mihome
```

If the user only wants the resource files locally, download the exact device resource version:

```bash
entroflow download --platform mihome --model <model> --version <version>
```

If the user wants the device to become usable through MCP, ask the user to confirm:

- `name`
- `location`
- `remark`

Then run:

```bash
entroflow setup --platform mihome --did <did> --model <model> --version <version> --name "<name>" --location "<location>" --remark "<remark>"
```

After setup succeeds, switch back to the MCP runtime tools.

## Notes

- If login expires, run `entroflow connect mihome` again.
- If a device model is shown as unsupported, stop and tell the user the device is not supported yet.
- If the local guide or behavior looks outdated, run:

```bash
entroflow update
```
