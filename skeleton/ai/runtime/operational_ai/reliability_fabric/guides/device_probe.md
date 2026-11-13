# device_probe — operational AI reliability and security

This domain validates claims emitted by a trusted local operator, resource
supervisor, installed-model verifier or durable state owner. It never
authenticates external evidence merely by parsing its JSON shape.

## Required fields

- `telemetry_known` — exact `bool` field with a finite schema budget
- `available_ram` — exact `int` field with a finite schema budget
- `required_ram` — exact `int` field with a finite schema budget
- `free_disk` — exact `int` field with a finite schema budget
- `required_disk` — exact `int` field with a finite schema budget

## Cross-field constraints

- Device telemetry must be measured.
- Available RAM fits operator floor.
- Private state disk has reserved capacity.

## Integration and qualification

Use `bindings/device_probe.py` to enforce the actual caller/model identity
before the record is considered admissible. No model-generated text may
choose a tool, replay an uncertain side effect, certify a release, or
override another tenant's consent. Store authoritative state in the
existing offline SQLite spine, not this process-local evidence ledger.

Run the 22 source-controlled cases, then run independent real native
GGUF model generation and target-device recovery before claiming
operational release. Checks `18` through `20` attack domain-specific
semantics; the first seventeen negative cases target envelope authority,
deadline, schema and resource bounds. No skipped CI gate counts as passed.

## Independent release holds

Model rights and source digests, Windows/WSL2 installation, locked
NativeBackend generation, hardware capacity and pressure, confirmed
cancellation, durable restart and all ten exact-final-head security/CI
checks remain outside this fixture's authority.
