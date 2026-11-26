# Source-leased original quest ending regression matrix

This Studio A vertical compares two **already compiled, original, typed quest revisions**
against the actual deterministic sandbox quest engine. It is a review workflow:
prompt -> typed original plan -> immutable private revision -> bounded ending
witnesses -> canonical comparison -> private receipt/HTML -> builder review.
It does not infer quest stages from natural language or grant native gameplay,
rights, hardware, or release certification.

## Operator flow

1. Author an original typed quest plan with the existing prompt quest CLI.
2. Save its source-verified compilation to a private directory.
3. Apply an explicit operator revision and persist the new compilation separately.
4. Invoke `python -m scripts.studio_quest_regression_matrix_cli --baseline-dir
   BEFORE --candidate-dir AFTER --expected-baseline DIGEST --expected-candidate
   DIGEST`. Optional `--max-states` and `--max-depth` control per-ending
   bounded search. `--html` emits CSP-protected read-only HTML; `--publish-dir`
   writes an exclusive, private, fsynced receipt in an existing private directory.
5. Review `proven_regressions`, `uncertain_endings`, and per-ending witness
   paths before compiling downstream gameplay. No automated release approval.

Jeeves exposes `studio_quest_regression_matrix` through the static
`studio_world_tool_router`. Request authority is out-of-band, not model-supplied.
The adapter performs no filesystem writes. Every result carries exact source
leases, deterministic witness evidence and a digest; replay recomputes both
compilations and all bounded witness searches.

A `found -> unreachable` or `found -> absent` change is a proven sandbox
regression only when the bounded search was exhaustive. `inconclusive` means
search budget exhaustion, never a proof of unreachability. Source changes require
review even when the shortest witness happens to remain identical. Paths are
compared deterministically; this does not prove native engine equivalence.

## Failure boundaries

Reject stale compilation leases, cross-project comparisons, malformed typed
requests, untrusted authority fields, oversized sources/receipts, tampered
canonical replay, non-private receipts, symlinks, hardlinks, duplicate JSON keys,
non-finite JSON, and publication overwrites. Do not downgrade any existing CI
or security release gate. Deterministic regression fixtures cover both source
revisions, real ending replay, budget uncertainty, tamper, publication, CLI and
Jeeves routing. Native gameplay qualification remains a separate hold.
