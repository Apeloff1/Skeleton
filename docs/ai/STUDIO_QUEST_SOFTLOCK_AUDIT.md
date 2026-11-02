# Studio A — Source-leased quest softlock audit

This vertical uses the canonical authored quest program and sandbox replay,
not static catalog inventory. Operators can propose an audit, author exact
target endings and bounded exploration budgets, persist a private receipt,
restore and replay it, and request a guarded sandbox handoff.

## Workflow

1. Obtain the exact `quest_source_digest` and initial session digest from
   `compile_quest_program` and `replay_quest` on the selected source.
2. Run `python -m scripts.studio_quest_softlock_audit_cli --project <id>
   --expected-source <sha256> --expected-session <sha256> --prompt`.
3. To edit, create a private JSON authoring object with exactly
   `initial_actions`, `target_endings`, `max_states`, `max_depth`,
   then pass `--authoring-file`. Target endings must exist in the source.
4. Publish only to an existing private directory with `--publish`; use
   `--restore` with the same source/session leases to verify it later.
5. `--html-preview` generates CSP-locked offline review. `--playable`
   returns a canonical quest replay handoff only when exploration exhaustively
   proves no terminal softlock and supplies a real eligible ending witness.

The analyzer uses deterministic breadth-first authored action expansion.
A terminal state with no selected ending proves a softlock, even when other
branches remain unexplored. A claim of no softlocks requires exhaustive
coverage; state/depth/queue exhaustion is inconclusive. Eligible endings are
monotonic under the canonical quest engine, so successful branches can be
pruned without losing a possible later softlock.

No native gameplay, audio, hardware, rights, release or physical-world
verification is claimed. Source digest leases and replay checks detect
accidental/hostile alteration; they are not cryptographic author signatures.
