# Matter Contact Sensor

This resource targets the standard Matter Contact Sensor device type.

Expected Matter shape:

- device type `0x0015`
- Boolean State cluster

Validated EntroFlow action surface:

- `query_status`

Notes:

- The runtime normalizes the raw boolean state into both `contact_detected` and a simple `open/closed` state string.
- Installation orientation still matters in the physical world, so verify the final semantic meaning during bench testing.

Verified models:

- No EntroFlow lab-verified retail models are recorded yet for this template.
