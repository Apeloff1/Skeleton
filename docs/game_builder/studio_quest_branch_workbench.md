# Studio A — source-bound quest branch workbench

This operator-facing workflow previews **only immediately legal authored choices**
from a deterministic canonical quest replay. A typed Jeeves request is a read-only
preview. An offline HTML review exports a candidate digest, never a permission
token. The CLI replays the authoritative source before accepting the selection.

## Workflow

1. Load a registered original studio project and compute
   `compile_quest_program(documents).source_digest` and
   `start_quest(documents, authorized=True).digest`.
2. Create a private mode-0600 JSON plan:
   `{"actions":[],"target_ending":"<authored ending id>"}`.
3. Run `python -m scripts.studio_quest_branch_workbench_cli --project <id>
   --expected-source <64-hex> --expected-session <64-hex> --plan-file plan.json`.
   The returned proposal lists every legal next authored choice and a
   canonical replay digest, with no automatic commit or publication.
4. Add `--review-html` for a CSP-restricted offline selection page.
   The exported private approval has exactly `schema`, `proposal_digest`
   and `candidate_digest` keys.
5. Re-run with `--approve --approval-file approval.json`. Optional
   `--publish <existing-private-directory>` creates an exclusive,
   fsynced `studio_quest_branch_checkpoint.json`. It never overwrites.
6. `--restore <directory>` revalidates private descriptor-anchored custody
   and recomputes the exact fork from current canonical source. Optional
   `--handoff` is allowed only when the authored target ending is eligible.

The CLI does not accept an approval as authority. Operator authorization is
out-of-band; the Jeeves router requires explicit `allow_authoring=True`.
Every receipt is source- and session-bound, size-limited, replay-verified, and
marked `release_certified=false`. A digest detects corruption, **not**
authorship. Sandbox ending eligibility does not prove native gameplay,
environmental evidence, device qualification, or rights clearance.

Focused regression: `pytest -q tests/test_studio_quest_branch_workbench.py`.
