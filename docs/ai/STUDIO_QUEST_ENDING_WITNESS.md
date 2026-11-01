# Source-bound authored ending witness

The operator chooses an existing original project, an authored ending, a
canonical quest session digest, a source digest and explicit state/depth
budgets. The planner expands **real quest alternatives** using the canonical
quest replay engine, returning the first deterministic witness in authored
stage/choice order. It never invents unobserved evidence. A budget-exhausted
search is **inconclusive**, not unreachable.

Inspect the selected catalog source and obtain its canonical leases first:\n\n```bash\npython -m scripts.studio_quest_ending_witness_cli --project PROJECT --inspect\n```\n\nExample (digests must be computed from the actual selected catalog project):

```bash
python -m scripts.studio_quest_ending_witness_cli --project PROJECT \
  --expected-source SOURCE_SHA256 --expected-session SESSION_SHA256 \
  --target-ending ENDING --max-states 512 --max-depth 16
```

An existing private directory can receive a single immutable, mode-0600
source-bound receipt via `--publish DIRECTORY`. Reopen with `--restore
DIRECTORY`; source/session drift, forged receipts, duplicate JSON keys,
symlinks and oversized input fail closed. `--html-preview` emits an
escaped CSP-restricted read-only witness. The Jeeves
`studio_original_quest_ending_witness` adapter accepts the same typed
request through the static world-tool registry. A witness proves only
sandbox quest-engine eligibility, not actual native gameplay, external
evidence, consumer device readiness or release certification.
