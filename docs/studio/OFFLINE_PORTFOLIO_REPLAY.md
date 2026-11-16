# Offline multi-cohort portfolio replay

This installed composition connects independent source-pinned batch replay
owners into a single read-only portfolio qualification. A canonical
portfolio.json contains schema skeleton.game_builder.offline_portfolio.v1
and ordered cohorts with cohort_id, directory and index_sha256. Each
directory is an ordinary canonical batch and contains its own pinned
batch.json and replayable original game packages.

Run python -m skeleton studio-portfolio-verify with --root,
--expected-index-sha256 and --trusted-local-operator. Optional
--receipt-output publishes a new compact receipt outside the source root.

Defaults allow 64 cohorts and 2048 packages, with a conservative byte
budget equal to 64 canonical batch ceilings. Maximum declared scale is
128 cohorts and 4096 package slots. These are admission limits, not
measured capacity. Every batch is independently replayed using the
original owner. All project identities must be globally unique and
cohort roots and indexes are fenced before and after replay. Every
cohort's declared worst-case replay byte budget is admitted up front.
No underlying package is rewritten. Prior batch receipts are never
used as a substitute for new replay.

The receipt binds the ordered cohort receipts, source pins, global project
set and exact aggregate counters. It does not imply a filesystem-wide
atomic snapshot, Godot or browser execution, rights clearance, release
authorization, or physical/device qualification. POSIX descriptor safety
is inherited from the canonical verifier. This wave adds real game fixture
regression source and selects it in the existing qualification workflow;
no test execution claimed until exact-head evidence exists.
