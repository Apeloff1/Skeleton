# Original quest branch review and playable handoff

Studio A source-bound branch comparison is a distinct, original-game authoring
vertical. It replays two **operator-authored** quest action histories using the
canonical `studio_ecosystem_quest` stage/choice engine. It does not invent
alternative choices, story endings, environmental evidence, player awards,
native runtime qualification or release proof.

## Workflow

1. Load a registered project through `read_blueprint`. Create two JSON files
   containing arrays of authored `[stage_id, alternative]` pairs, with private
   file permissions (0600).
2. Run `python -m scripts.studio_quest_branch_review_cli --project PROJECT
   --left-actions /private/left.json --right-actions /private/right.json
   --target-ending ENDING` to obtain a typed editable plan and comparison.
3. Save the `review.authoring` JSON as a private plan. Edit `selected`,
   `review_note`, and `reviewed`; alternatively render `--editor-html`,
   review offline, and export the edited plan. Browser output is never trusted.
4. Compile `--plan /private/plan.json --handoff`. The selected route must be
   canonically replayable, explicitly reviewed, and eligible for the selected
   ending. Otherwise the handoff fails closed.
5. Use `--publish /private/empty-dir` to atomically create an exclusive
   source-bound receipt. Use `--restore /private/dir` to verify the exact
   canonical replay against the current source before using it.

A handoff contains canonical choices, source/session digests, selected ending,
and an independently recomputed receipt digest for a downstream playable
adapter. The adapter must not interpret these as physics, external-evidence,
player-consent, rights, or device acceptance.

## Failure policy

Unknown stage or choice, changed source, malformed plan, duplicate/unreviewed
fields, mismatched receipt, stale initial session, forged eligibility, oversized
input, symlinked private input, existing output, and unauthorized requests
are rejected. Branch comparison is bounded to 64 actions per branch and the
canonical authored DAG limit. The HTML editor uses a pinned CSP script hash,
escapes authored content, and cannot access the network.
