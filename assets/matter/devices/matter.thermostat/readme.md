# Matter Thermostat

This resource targets the standard Matter Thermostat device type.

Expected Matter shape:

- device type `0x0301`
- Thermostat cluster

Validated EntroFlow action surface:

- `set_mode`
- `set_heating_setpoint`
- `set_cooling_setpoint`
- `query_status`

Notes:

- The resource exposes only the core runtime controls that are broadly stable across Matter thermostats.
- Scheduling, occupancy presets, and vendor-specific HVAC features are intentionally omitted.

Verified models:

- No EntroFlow lab-verified retail models are recorded yet for this template.
