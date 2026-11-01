# Portable combat campaign saves

`python -m skeleton combat-campaign-package demo` emits an original
Lantern Harbor patrol checkpoint after the first encounter. The package
contains canonical authored source, a verified combat campaign snapshot,
the nested combat journals, deterministic source/state digests, save
lineage, and a compact human-readable progress manifest.

`combat-campaign-package pack --source-json '<canonical-source>'
--session-json '<checkpoint>'` rejects any save that cannot be fully
replayed against its own source, or whose source differs from the supplied
canonical source. `combat-campaign-package verify --package-json '<bundle>'`
replays and compares the complete portable artifact. `combat-campaign-package
resume --package-json '<bundle>'` finishes only verified incomplete
checkpoints; terminal checkpoints are idempotent.

Exports are capped at 128 KiB, reject duplicate JSON keys and nonfinite
constants, and never interpret embedded content as executable code.
Receipts and digests detect accidental or malicious drift only when the
trusted source is held separately; they do not prove authorship or grant
permissions. External provenance and publication policy remain mandatory.
