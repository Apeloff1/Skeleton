# Studio A — source-leased quest replay repair

The existing diagnostic locates the first invalid authored quest action and
produces a canonical legal-prefix witness. This vertical turns that evidence
into a bounded **operator-reviewed repair selection**, without silently
rewriting choices or treating sandbox replay as native gameplay.

## Flow

1. Obtain the registered project, canonical quest source digest and initial
   session digest. Author a private JSON diagnostic request with
   `actions`, `target_ending` and `expected_final_session_digest`.
2. Run `python -m scripts.studio_quest_replay_repair_cli --project PROJECT
   --expected-source DIGEST --expected-session DIGEST --plan-file FILE`.
3. Inspect the deterministic candidate list. The first candidate truncates
   at the first invalid action. Other candidates replace that one action
   with one of the next canonical legal actions and drop the entire stale tail.
4. `--review-html` emits a CSP-hashed offline selection UI. Its export is
   an unsigned JSON approval request, not proof or a published save.
5. Supply a private JSON approval with the proposal digest and the selected
   candidate digest. Invoke `--approve --approval-file FILE`. The compiler
   replays the original source and selected repair and returns the ordinary
   quest diagnostic receipt. `--publish DIR` uses the existing exclusive,
   private diagnostic writer. `--handoff` is allowed only if the selected
   replay actually satisfies the target ending.
6. Jeeves exposes only the source-bound preview through the static tool
   `studio_original_quest_replay_repair`. Operator authoring opt-in remains
   out of band. Models cannot approve or publish through this tool.

## Boundaries

The candidate set is finite and source-derived. Forged receipts, stale
leases, unknown selections, missing operator authority, invalid source,
oversized reports and replay drift fail closed. Unselected tail actions are
never retained implicitly. No external evidence, rights, native gameplay,
or release certification is inferred.

Focused regression module: `tests/test_studio_quest_replay_repair.py`.
Run exact-head canonical pytest, security/architecture gates and CI before
review promotion or release.
