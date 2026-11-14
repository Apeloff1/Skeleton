# Portable weather journey checkpoints

`python -m skeleton scene-weather-package demo` produces a checkpoint
after the original Lantern Harbor key pickup. The package includes canonical
authored weather/scene source, a replay-verifiable nested scene save, full
weather event journal, source and save digests, and a compact manifest
containing location, inventory, weather, tick and phase.

Use `pack --source-json '<source>' --session-json '<session>'` to export;
`verify --package-json '<bundle>'` to recompute all canonical transitions;
`resume --package-json '<bundle>' --actions-json '<actions>'` to continue
through real weather collision and inventory gates. Empty action batches
return the identical verified package; invalid or terminal transitions fail
without mutating the supplied checkpoint.

The package is bounded to the canonical 128 KiB JSON limit. Duplicate JSON
keys, nonfinite values, altered receipts, mismatched source, forged pickups,
weather drift and save-lineage changes are rejected. The manifest is
observational; it cannot award inventory or force a victory. A digest is not
an authenticity signature, and this offline feature does not establish
consumer/device release qualification.
