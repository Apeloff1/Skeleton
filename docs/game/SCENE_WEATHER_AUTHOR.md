# Weather authoring with playable route preview

`python -m skeleton scene-weather-author demo` edits the original
Lantern Harbor storm cycle and returns a source-bound replayable route
preview. `edit` accepts `--source-json`, `--operations-json`,
`--expected-digest`, `--max-states` and `--max-depth`.
The digest must equal the normalized source digest. Edits are atomic,
bounded to 16 operations, and reject no-ops, invalid gates, unsupported
conditions, duplicate gates, unknown exits and stale source revisions.

Operations are `set-cycle` (ordered weather conditions),
`set-gate` (scene, exit, blocked conditions), and `remove-gate`.
The full edited source is normalized before any preview. The preview
uses the canonical scene-weather route solver, real movement/collision,
inventory prerequisites, deterministic save lineage and replay verification.
An exhausted search reports `inconclusive`, never a fabricated win.

`verify --source-json '<original>' --receipt-json '<receipt>'`
replays the entire authoring transaction and gameplay preview. Neither
the original source nor filesystem is modified. Integrity digests do
not prove authorship or grant authorization; consumer and device
qualification remain separate release gates.
