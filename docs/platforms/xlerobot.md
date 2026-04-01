# XLeRobot Platform Guide

Use this guide when the user wants to control a locally running XLeRobot host.

The generic CLI and MCP flow lives in the local `skill.md`. This guide only
covers XLeRobot-specific runtime assumptions and setup requirements.

## Platform Identity

- platform id: `xlerobot`
- current validated device resources:
  - `xlerobot.3wheel`
  - `xlerobot.2wheel`

## Important Difference From Cloud IoT Platforms

`xlerobot` is not a cloud account connector.

There is no QR login and no browser-based account authorization flow.

EntroFlow only talks to the already running XLeRobot ZeroMQ runtime.
It does not replace the upstream LeRobot environment, the upstream host, the
web UI, or the RoboCrew LLM layer.

## Expected Local Workspace

Default root:

```text
~/XLeRobot/software
```

The operator should already have:

- the XLeRobot repository cloned locally
- the upstream LeRobot-compatible environment prepared
- the correct hardware variant assembled and calibrated
- the matching host process running

## Recommended Host Commands

3-wheel omni base:

```bash
cd ~/XLeRobot/software
PYTHONPATH=src python -m lerobot.robots.xlerobot.xlerobot_host --robot.id=my_xlerobot
```

2-wheel differential base:

```bash
cd ~/XLeRobot/software
PYTHONPATH=src python -m lerobot.robots.xlerobot_2wheels.xlerobot_2wheels_host --robot.id=my_xlerobot_2wheels
```

## Runtime Profiles

EntroFlow reads:

```text
~/.entroflow/runtime/xlerobot_profiles.json
```

If the file is missing, EntroFlow falls back to these singleton defaults:

- `xlerobot-3wheel-local` for `xlerobot.3wheel`
- `xlerobot-2wheel-local` for `xlerobot.2wheel`

Example custom profile file:

```json
[
  {
    "did": "xlerobot-3wheel-lab",
    "name": "XLeRobot Lab Omni",
    "model": "xlerobot.3wheel",
    "host": "192.168.1.123",
    "port_cmd": 5555,
    "port_observations": 5556
  },
  {
    "did": "xlerobot-2wheel-lab",
    "name": "XLeRobot Lab Differential",
    "model": "xlerobot.2wheel",
    "host": "192.168.1.124",
    "port_cmd": 5555,
    "port_observations": 5556
  }
]
```

## Setup Notes

If the user only wants the resource files locally, download the exact device resource version:

```bash
entroflow download --platform xlerobot --model xlerobot.3wheel --version <version>
entroflow download --platform xlerobot --model xlerobot.2wheel --version <version>
```

If the user wants the device to become usable through MCP, during `entroflow setup`
the user must still confirm:

- `name`
- `location`
- `remark`

Suggested example:

```bash
entroflow setup --platform xlerobot --did xlerobot-3wheel-local --model xlerobot.3wheel --version <version> --name "Kitchen XLeRobot" --location "Kitchen Lab" --remark "3-wheel omni prototype"
```

## Safety Notes

- Start the upstream host before running `entroflow connect xlerobot`.
- Do not treat `move_base` as autonomous navigation.
- Do not expose model training, RoboCrew, or VLA inference as the device runtime surface.
- The 2-wheel model does not support lateral `y` motion.
- If joint calibration or neutral pose safety is unclear, stop and ask for human confirmation.
