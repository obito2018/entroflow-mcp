# Matter Color Temperature Light

This resource targets the standard Matter Color Temperature Light class used by many tunable white lamps and bulbs.

Expected Matter shape:

- device type `0x010C`, or an extended-color light endpoint reused through this reduced template
- On/Off cluster
- Level Control cluster
- Color Control cluster with color temperature support

Validated EntroFlow action surface:

- `turn_on`
- `turn_off`
- `toggle`
- `set_brightness`
- `set_color_temperature`
- `query_status`

Notes:

- This template intentionally exposes the tunable-white subset only.
- Extended-color lights can reuse this template when the desired EntroFlow surface is still just power, brightness, and color temperature.

Verified models:

- No EntroFlow lab-verified retail models are recorded yet for this template.
