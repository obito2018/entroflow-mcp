# Matter Smart Plug

This resource targets the standard Matter smart plug / on-off plug class.

Expected Matter shape:

- device type `0x010A`
- On/Off cluster

Validated EntroFlow action surface:

- `turn_on`
- `turn_off`
- `toggle`
- `query_status`

Notes:

- The resource intentionally models the plug as a simple atomic power endpoint.
- Metering, vendor scenes, and platform-specific extras are not exposed here.

Verified models:

- No EntroFlow lab-verified retail models are recorded yet for this template.
