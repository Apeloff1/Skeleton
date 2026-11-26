# Source-bound quest localization (Studio A)

The Jeeves tool \`studio_original_quest_localization\` prepares **editable source
labels**, not purported machine translations. Every stage ID, alternative,
reward and ending comes from the exact canonical original quest. Operator
authorization and source/session digests are mandatory.

## End-user flow

1. Load an original catalog blueprint with
   \`read_blueprint("studio_puzzle_expedition_copper_mesa")\`, compile its
   \`compile_quest_program\` and \`start_quest\` leases.
2. Ask Jeeves for the localization proposal with locale \`nb-NO\`,
   canonical actions, ending and exact source/session digests. Tool routing
   requires both \`authorized=True\` and \`allow_authoring=True\`.
3. Save the proposal as a private 0600 JSON file. Edit \`translation\` for
   each exact source row and mark \`reviewed=true\` only after human review.
   Source keys, ordering, stage IDs and choice semantics must remain intact.
4. Run \`python -m scripts.studio_quest_localization_cli --project
   studio_puzzle_expedition_copper_mesa --expected-source DIGEST
   --expected-session DIGEST --plan-file /private/plan.json --editor-html\`
   for the offline CSP-protected editor. Export edited JSON and recompile.
5. Run the same CLI with \`--publish /private/directory\` for an exclusive
   0600 receipt; \`--restore /private/directory\` replays its canonical
   source. \`--handoff\` is admitted only when every row is reviewed and
   the selected ending is canonically eligible.

## Security and acceptance

The source-bound lease invalidates translations when the authored quest
changes. Translated display strings cannot alter the canonical action keys,
earned choice effects or ending predicates. Replayed receipts are recomputed,
not trusted. The CLI uses descriptor-anchored private JSON input, refuses
symlinks, duplicate JSON keys and stale directory identity, and writes an
exclusive publication with rollback. HTML is escaped, network-disabled and
uses a pinned CSP script hash. Bidi controls and unsafe Unicode controls are
rejected. Review is an operator assertion, **not translation provenance
attestation**. No native game runtime, external evidence, device acceptance
or release qualification is claimed. Focused regressions:
\`pytest tests/test_studio_quest_localization.py\`.
