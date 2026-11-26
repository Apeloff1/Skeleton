# Source-replayed quest ending causal provenance (Studio A)

This vertical explains **why** a selected original authored quest ending is
eligible or blocked in the canonical sandbox. It never invents observations,
native gameplay proof, provenance signatures, or release acceptance.

## Operator workflow

1. Prepare a private `actions.json` containing
   `{"actions":[["stage_id","authored_alternative"]]}` with mode 0600.
2. Run `python -m scripts.studio_quest_cause_trace_cli --project PROJECT
   --actions-file actions.json`. The typed plan has `reviewed=false`.
3. Run the same proposal command with `--editor-html` to obtain a CSP-bound offline interactive review page. It exports a selected-endings plan but does not compile or persist anything itself. Review the exact stage order, ending IDs, and source/session digests.
   Change **only** `reviewed` to `true`, or narrow `target_endings` to
   the subset requiring an explanation. Save private `plan.json`.
4. Run `python -m scripts.studio_quest_cause_trace_cli --project PROJECT
   --plan-file plan.json --publish PRIVATE_DIRECTORY`. The directory must
   exist, be privately owned, and have secure permissions. Existing receipts
   are not overwritten.
5. Run `python -m scripts.studio_quest_cause_trace_cli --project PROJECT
   --restore PRIVATE_DIRECTORY --html` to view the offline CSP-protected
   explanation. For a replay-verified handoff use `--handoff` instead.

The trace maps each ending predicate to the **first** canonical action that
earned it, including stage identity, authored reward and explicit
choice-effect tokens. Duplicate earned rewards retain the first witness.
Unmet predicates remain unmet; they cannot be filled by prose. Every frame
includes previous/next session digests, stage prerequisites, and earned tokens.

Jeeves can register `register_quest_cause_tools(registry, documents)`.
The registered tools are read-only and require explicit authority:
`studio_quest_cause_proposal`, `studio_quest_cause_compile`, and
`studio_quest_cause_handoff`. Registration freezes the source identity;
mutating the supplied documents invalidates the tool.

## Security and qualification boundaries

All inputs are source-leased, typed and bounded. Private JSON reads reject
symlinks, directory swaps, duplicate keys, nonfinite values, loose
permissions and oversized files. Publication is no-overwrite, descriptor-
anchored and fsynced. Receipts are replayed against the authoritative quest
source on restore and before any handoff. A SHA-256 digest is an integrity
checksum, **not** an author signature. A verified authored causal explanation
is not a game-engine, device, or release certification.

Focused regressions:
`tests/test_studio_quest_cause_trace.py` and
`tests/test_studio_quest_cause_trace_jeeves.py`.

The handoff re-invokes the canonical HTML5 preview compiler and verifies its
project identity, gameplay proof flag, and exact HTML SHA-256. This is a
source-bound playable HTML5 handoff, not proof of native engine behavior.
