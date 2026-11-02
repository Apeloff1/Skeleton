# Studio A — canonical quest readiness (sandbox only)

This source-complete vertical connects the operator's typed prompt to two
independently compiled proofs: **all authored endings have legal replay
witnesses**, and **no terminal authored quest branch is softlocked** under
an exhaustive bounded exploration. Neither condition alone is sufficient.

The compiler refuses partial ending selections and nonempty replay prefixes.
It checks source and initial-session SHA-256 leases, validates exact typed
exploration budgets, and fails closed on exhaustion. If a proof cannot complete
within 2,048 states, it reports an inconclusive hold instead of asserting safety.

## Operator flow

1. Read the canonical registered project blueprint, compile its quest program,
   and obtain the exact `source_digest` and empty `start_quest(...).digest`.
2. Run `python -m scripts.studio_quest_readiness_cli --project PROJECT
   --expected-source DIGEST --expected-session DIGEST --prompt`.
3. For a custom bounded exploration, supply a private JSON budget file
   `{"max_states":512,"max_depth":12}` with `--budget-file PATH`.
4. Use `--html-preview` for a script-free static proof report.
5. Use `--publish EXISTING_PRIVATE_DIRECTORY` for an exclusive fsynced
   source-replayable receipt; `--restore DIRECTORY` rechecks it against
   current canonical source. Existing files are never overwritten.
6. Use `--playable` only when the combined proof is ready. It produces a
   canonical sandbox handoff referencing independently replayed proof digests.
   It does **not** certify native gameplay, external evidence, rights or release.

Jeeves read-only tool `studio_original_quest_readiness` accepts
`skeleton.jeeves.studio_quest_readiness_request.v1` with `project_id`,
`authoring`, `expected_source_digest`, and
`expected_initial_session_digest`. The static router requires out-of-band
operator authorization; the request cannot grant itself write permission.

## Invariants and failure cases

* Every ending in the source must be witnessed independently, not merely one.
* Terminal branches with no eligible authored ending block handoff even when
  other branches witness every ending.
* Unknown coverage, truncated search and stale source/session leases block.
* Replayed proof digests bind source, budget, witnesses and terminal audit.
* Receipt restoration rejects symlinks, hard links, non-private files, duplicate
  JSON keys, nonfinite values, truncation and in-place file changes.
* The static HTML preview has no JavaScript, network or write capability.
* The entire flow is deterministic and bounded; it does not invoke a model.

Focused regression entry points:
`tests/test_studio_quest_readiness.py` and
`tests/test_studio_quest_readiness_integration.py`.

**Release hold:** source correctness, actual test execution, native game
simulation, consumer-device qualification, provenance and exact-head CI remain
separate gates. A cryptographic digest is an integrity identifier, not an
authenticated signature.
