# Original quest remap proposals — Studio A

A saved authored quest can become stale when an operator revises choice prose.
The migration compiler intentionally refuses to infer approval. This vertical
adds a deterministic, source-leased *proposal* that identifies only changed
selected alternatives by their immutable stage and positional identity.

## End-user flow

1. Obtain the canonical quest source digest and initial session digest from
   the registered blueprint and `start_quest`. Author a canon-reviewed revision
   request and an old, fully legal quest replay action list.
2. Put `{"revision_request":...,"actions":[...],"target_ending":"..."}`
   into a private JSON file (POSIX mode 0600). Run
   `python -m scripts.studio_quest_remap_proposal_cli --project PROJECT --expected-source DIGEST --expected-session DIGEST --plan-file FILE`.
3. Inspect the candidate list and source digest. Use `--review-html` to
   generate an offline, CSP-locked editor. Browser export is **not approval**.
   The UI never sends network requests or claims playable/native proof.
4. Review every proposed `stage_id/from_choice/to_choice` pair. Supply a
   private JSON approval export containing `schema`, `proposal_digest`, and
   the exact reviewed `remaps`. Run the CLI with `--approve --approval-file FILE`.
5. The compiler replays the entire proposal from canonical source, checks
   every remap, recompiles the revised quest and verifies the new session.
   Only a fully migrated, eligible ending can receive `--handoff`.
   `--publish DIR` uses the existing exclusive private migration receipt
   writer; never overwrites a prior receipt.

Jeeves exposes only the typed, read-only preview tool
`studio_original_quest_remap_proposal`, requiring explicit out-of-band
authoring permission. A model-generated request cannot approve a migration.

## Failure and assurance boundaries

- Stale source/session/proposal digests, invalid or partial remaps, duplicated
  stages, forged approvals, missing authority and oversized payloads fail closed.
- The old and revised canonical quest are recompiled and replayed; the
  protected graph and ending semantics remain enforced by the migration
  compiler. A proposal never mutates the source or writes files.
- Native gameplay, external authorship, asset rights and release readiness
  remain unverified. The HTML editor's export is not a cryptographic signature.
- Regression fixtures: `tests/test_studio_quest_remap_proposal.py`.
  Execute canonical focused pytest and all final-head CI before promotion.
