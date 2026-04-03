# Matter Door Lock

This resource targets the standard Matter Door Lock device type.

Expected Matter shape:

- device type `0x000A`
- Door Lock cluster

Validated EntroFlow action surface:

- `lock`
- `unlock`
- `query_status`

Notes:

- Lock and unlock use the standard Matter lock commands and therefore preserve the vendor's own access control logic.
- PIN workflows, schedules, and credential management are intentionally outside this runtime template.

Verified models:

- No EntroFlow lab-verified retail models are recorded yet for this template.
