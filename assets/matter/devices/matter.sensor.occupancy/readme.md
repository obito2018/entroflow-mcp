# Matter Occupancy Sensor

This resource targets the standard Matter Occupancy Sensor device type.

Expected Matter shape:

- device type `0x0107`
- Occupancy Sensing cluster

Validated EntroFlow action surface:

- `query_status`

Notes:

- Occupancy is normalized to a simple boolean for agent-friendly reasoning.
- Delay tuning and raw sensor diagnostics are intentionally omitted.

Verified models:

- No EntroFlow lab-verified retail models are recorded yet for this template.
