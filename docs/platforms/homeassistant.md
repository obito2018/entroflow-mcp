# Home Assistant Platform Guide

## Before connecting

Read this platform guide before running `entroflow connect homeassistant`.

Home Assistant uses command-line token authentication. EntroFlow does not use a web login page for this platform.

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

The command validates the token against Home Assistant and stores the credential locally in EntroFlow runtime storage.

## Verify

```bash
entroflow list-devices --platform homeassistant
```

If the command cannot reach Home Assistant, check that the URL is reachable from the machine running the agent and that the token is still valid.
