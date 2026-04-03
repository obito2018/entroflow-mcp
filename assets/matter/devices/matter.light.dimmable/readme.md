# Matter Dimmable Light

This resource targets the standard Matter Dimmable Light device type.

Expected Matter shape:

- device type `0x0101` on a usable endpoint
- On/Off cluster
- Level Control cluster

Validated EntroFlow action surface:

- `turn_on`
- `turn_off`
- `toggle`
- `set_brightness`
- `query_status`

Notes:

- Brightness is normalized to `1~100` for agent-friendly control.
- This template does not expose vendor scenes or composed lighting workflows.

Verified models:

- No EntroFlow lab-verified retail models are recorded yet for this template.
