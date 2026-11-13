# Cooperative playthrough comparison

Use `python -m skeleton scene-market-party-compare demo` to play an
original authored cooperative market campaign, compare it with an alternate
decision, and explicitly select the earned winning branch for portable export.

`compare --left-json JSON --right-json JSON` replays both canonical
checkpoints and checks identical authored source identity. The report
includes the exact common journal prefix, the first divergent turn,
remaining turns, credits/goods differences, earned phase and role
contributions. The report is deterministic and can be independently checked
with `verify --left-json JSON --right-json JSON --receipt-json JSON`.

`select --left-json JSON --right-json JSON --choice left|right
--expected-left-digest SHA --expected-right-digest SHA` enforces explicit
optimistic leases on both branches, exports only the selected canonical
checkpoint and verifies its portable round trip. Use `verify-selection`
to independently reconstruct a selection receipt.

A branch is never merged into another branch, a victory is never
manufactured, and no economy state is mutated by comparison. Report
checksums prove reproducible integrity, not author identity. The
canonical party turn budget and two-MiB report budget remain enforced.
