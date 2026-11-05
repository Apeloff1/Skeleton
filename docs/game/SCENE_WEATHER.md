# Deterministic Scene Weather Production

`python -m skeleton scene-weather demo` runs an original playable survival
journey through the canonical tile, scene and survival reducers. Weather is
authored inert JSON, never code. Each scene has a finite cyclic forecast; moves
consume stamina and can inflict damage. Equipment must be collected through a
canonical pickup before it can be equipped. Movement collision, terminal
endings, food and shelter remain owned by the underlying survival runtime.

Use `scene-weather simulate --source-json JSON --actions-json JSON` to run
authored content; `resume --session-json JSON --actions-json JSON` to continue
a verified checkpoint; `verify`, `export` and `import` to validate or
transport portable replay receipts. Export checksums detect accidental
corruption and replay tampering, **not** malicious reauthoring of both source
and receipt. Trusted source identity must be pinned by the caller.

Use `scene-weather-author edit --source-json JSON --edits-json JSON
--expected-digest SHA256` for all-or-nothing climate/equipment edits, and
`scene-weather-author preview` to exercise the same canonical reducer before
publication. Editing refuses stale source digests, unknown scene IDs, malformed
weather phases, unearned equipment, oversize inputs and partial edit batches.

The runtime uses bounded 256-step journals, 256 KiB authored-source budgets,
2 MiB checkpoint budgets, explicit schema versions, exact object fields,
stable sorted equipment, canonical replay, parent-save digests and fail-closed
collision. No wall clock, network, native renderer or nondeterministic RNG.
A checkpoint cannot substitute for external authentication or consumer/device
qualification. Regression tests cover movement, source provenance, rest,
equipment, replay, save/export/import, editor CAS and forged receipts.

For a stream-based user interface, run `python -m skeleton scene-weather-play play --source-json JSON`. Commands include `move east`, `collect find_key`, `equip stormcloak`, `rest` and JSON actions. The adapter emits replay-verified checkpoints at configurable intervals and on EOF or input exhaustion. No input is executed as code.
