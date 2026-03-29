# Mi Home Platform Guide

Use this guide when the user wants to connect Xiaomi Mi Home / Mijia.

## Platform Identity

- platform id: `mihome`
- common aliases: `mijia`, `xiaomi`, `mi home`, `米家`, `小米`

Always use the platform id `mihome` in CLI commands.

## When To Use This Platform

Choose `mihome` when the user's account and devices are managed through the Mi Home app.

Examples:

- Xiaomi smart lights
- Xiaomi sensors
- Xiaomi home appliances that appear inside Mi Home

## Connection Flow

1. Run:

```bash
entroflow connect mihome
```

2. The CLI will try to open the login URL in the default browser automatically.
3. If the browser does not open, use the printed URL manually.
4. Complete the login confirmation in the Mi Home app.
5. After the user confirms the login, continue the CLI flow until it reports success.

## After Connection

After the platform is connected:

1. Run:

```bash
entroflow list-devices --platform mihome
```

2. Ask the user which exact device should be set up.
3. Ask the user to confirm:
   - `name`
   - `location`
   - `remark`
4. Run:

```bash
entroflow setup --platform mihome --did <did> --model <model> --name "<name>" --location "<location>" --remark "<remark>"
```

5. After setup succeeds, switch back to the MCP runtime tools.

## Notes

- If login expires, run `entroflow connect mihome` again.
- If a device model is shown as unsupported, stop and tell the user the device is not supported yet.
- If the user expects a newer Mi Home integration behavior but the local guide looks outdated, run:

```bash
entroflow update
```
