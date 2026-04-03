# Matter On/Off Light

This resource targets the standard Matter On/Off Light device type.

Expected Matter shape:

- device type `0x0100` on a usable endpoint
- On/Off cluster

Validated EntroFlow action surface:

- `turn_on`
- `turn_off`
- `toggle`
- `query_status`

Notes:

- This template intentionally exposes only the atomic light power controls.
- If a real product also supports level or color temperature, EntroFlow should use a richer Matter light template instead.

Verified models:

- No EntroFlow lab-verified retail models are recorded yet for this template.
