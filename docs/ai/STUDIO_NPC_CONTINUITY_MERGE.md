# NPC continuity branch reconciliation

The source-bound continuity merge is an **annotation-only** vertical. It
accepts two canonically replayable NPC continuity journals from the same
project, source, quest session and knowledge-exchange ancestry. Every scene,
transit, meeting, earned fact, timestamp and proof digest must match.

`scripts/studio_npc_continuity_merge_cli.py` accepts `--project`,
`--expected-source`, `--baseline` and `--candidate` JSON receipts.
Use `--prompt` to obtain a typed deterministic review. Non-conflicting
notes are carried forward; different nonempty notes on the same event are
**not silently selected**. Provide `--decisions` with
`{"decisions":[{"event_key":"scene:...","take":"candidate"}]}`.
The only valid choices are `baseline`, `candidate` and `drop`.
Unresolved conflicts can be inspected and persisted, but **cannot** be
compiled into a playable handoff.

The `--editor-directory` option creates an immutable private, CSP-hashed
offline HTML editor. It exports typed JSON only. The CLI's
`--import-decisions` and `--baseline-merge` pair verifies the source,
session, both branch digests and baseline merge digest before replay.
`--publish` and `--restore` use descriptor-anchored private, exclusive
file publication. The Jeeves static router exposes
`studio_original_npc_continuity_merge`; it does not accept model-supplied
authorization or create files. Native scene playback, speech, hardware,
consumer readiness and release certification are explicitly unverified.

Focused regression contract:
`pytest -q tests/test_studio_ecosystem_npc_continuity_merge.py`.
