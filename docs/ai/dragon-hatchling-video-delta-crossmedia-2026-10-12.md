# Dragon hatchlings — video, update and cross-media mother research
**Authored:** 2026-10-12 UTC · **Target:** `Apeloff1/Skeleton` PR #3605.

## Milestone 1 — Video hatchling: timecoded transcript evidence

`DragonVideoTranscriptLedger` adds an owner-bound, SQLite-backed, bounded video transcript review ledger that is separate from copyrighted media downloads. It accepts timecoded cue objects (up to 64 short cues, 16 KB total, and a 12-hour timeline bound) for a canonical registered YouTube/Vimeo video source. The track hash is computed over ordered exact cues. An **external Ed25519 reviewer** must sign the exact owner, source URL and ID, transcript track hash, reference-permission evidence digest and short expiry, explicitly scoped to `timecoded_transcript_reference_only`.

A staged receipt requires a **real granted video hatchling ticket**, current global resource admission, five-minute idle status, and explicit *video* consent. It performs no media I/O, never fetches platforms, and releases its synchronous RAM/CPU reservation on completion or denial. Every staged cue is retained in an append-only digest-verified revision history with precise UTC observation time and an `(improvement)` note; an unchanged transcript or repeated attempt cannot generate growth.

Read-only `review_packet` hides all quote text by default. An explicitly authorized local reviewer can request exact cues with their start/end millisecond offsets, capture digest, evidence-license attestation digest and source identity. This stage never grants Wikipedia/Wiki authority, HOAG model training or companion XP. The external signing key must stay outside the Dragon; signatures authenticate a rights-review assertion, not the existence of legal rights by themselves.

## Milestone 2 — Updates hatchling: exact changed-source observations

`DragonSourceDeltaLedger` builds a bounded, deterministic comparison of the **real** governed `DragonSourceCaptures` history. Only actual changed source bytes produce a review proposal; an unchanged recrawl returns `unchanged_reobservation` and creates no delta, XP or shadow weights.

Source edits are indexed by exact before/after text spans. The review packet tags lexical *warning triggers*, such as API compatibility, correctness, performance, rights, security and gameplay; these are questions for a reviewer rather than a machine-generated factual verdict. Output includes original and new capture/content digests, observation time, total changed operations, up to 12 exact changes, explicit truncation status and questions for independent source verification. If a document is too large for a reliable bounded comparison, the algorithm refuses automatic analysis rather than silently summarizing away possible changes.

`stage_idle` requires a real *updates-lane* worker ticket from the signed nest and global resource admission, separately consented for updates, still idle and bound to the canonical source. It writes a replay-safe, owner-bound, append-only changed-revision journal only after revalidating the current source-capture head. The ticket's shared CPU/RAM reservation is released when the synchronous stage finishes. A later capture superseding the staged delta requires fresh analysis; the read-only review packet refuses stale work.

Trusted source-delta inspection:
```sh
python -m skeleton.ai.game_builder.dragon_technical_source_cli delta-preview \
  --database /approved/dragon.sqlite --owner studio \
  --source-id source-<64hex> --trusted-local-operator

python -m skeleton.ai.game_builder.dragon_technical_source_cli delta-review \
  --database /approved/dragon.sqlite --owner studio \
  --source-id source-<64hex> --trusted-local-operator
```

## Milestone 3 — Mother Dragon's cross-media insight proposals

`DragonMotherEvidenceSynergy` takes **two different authenticated sources**, one staged video transcript and one source-update comparison, then computes conservative overlapping vocabulary across the timecoded cues and the new article's *exact* changed passages.

Every suggested bridge includes exact original video and article wording and offsets, the two custody receipt IDs, overlap terms and an unanswered reviewer question. It explicitly declares `source_independence_verified=false` and `content_agreement_verified=false`; two sources discussing the same term is not independent corroboration or a fact. The mother produces a task-aware **review-navigation packet**, not a model weight or XP event. Maximum output is 12 links and 16 terms per evidence bridge.

The existing `DragonNestReviewBridge` remains the sole companion growth path, dependent on the separate `ReviewedKnowledgeStore` and its independent verification. Approved knowledge must traverse the separate Wiki and HOAG controls. Neither video staging nor update comparison overrides those requirements.

## Regression plan / status

`tests/test_dragon_specialist_evidence.py` includes 11 test cases for externally signed video cue ingestion under a real global grant, exact timecodes and masked review packets, idempotency, unchanged text, signature and scope refusal, tamper/tenant isolation, actual source-change detection, idle updates-lane admission, cross-media research links and missing-authority refusal. The Dragon AI Verification workflow compiles all three new modules and explicitly runs that test module in both its broad and focused suites. A discoverable `test_ai_dragon_source_safety.py` smoke test covers imports in older base workflows.

These are **authored implementation tests**, not proof of successful CI execution. Current PR code is not deployed; no live source, copyrighted video, or neural model was downloaded/trained during this pass.

## Safety and remaining implementation

External transcription ingestion needs a separately licensed transcript provider or an authorized user-created transcript, independent signer identity verification, and a job transport from the actual host app. Historical source recrawls must still obtain current robots/terms approval. UI integration should display timecodes, changed passages and review questions without presenting unverified hypotheses as authoritative information. Cross-media matching is intentionally lexical, not a claim that the system understands semantic agreement.

**Timestamped improvements:** 2026-10-12 UTC — (added source-exact timecoded video evidence), (added lawful signed transcript review scope), (added bounded changed-revision delta scrutiny), (added mother cross-media research prompts with no fake corroboration), (preserved idle-only CPU/RAM discipline and independent Wiki approval).
