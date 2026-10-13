# Safe Godot materialization and pre-publication playtest

The canonical projector rejects path traversal, Windows device files, case
aliases, embedded metadata/evidence overwrites, non-text files, and symbolic
links before committing generated output. Newly created trees are staged beside
the destination and published atomically. Existing trees require explicit
`--overwrite` for any collisions, and unrelated files are preserved.

`--playtest require` checks the headless Godot boot *before* publishing the
project; failure/unavailability does not create a new output directory.
`--playtest auto` can still emit, while preserving unavailability as evidence.

The final `CONTEXT_LEDGER.json`, `CONTEXT_TENSOR.json`, and
`build_report.md` are staged as validated UTF-8 evidence after the seal.
Outputs do not follow symlinks. Existing evidence is replaced with per-file
atomic operations, rather than truncating a previous ledger through an unsafe
file handle. An invalid evidence destination fails the seal stage.
