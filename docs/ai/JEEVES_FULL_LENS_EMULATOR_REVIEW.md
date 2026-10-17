# Jeeves full-catalog emulator lens review — operator contract

**Scope:** replay-audited ROM learning -> complete existing lens catalogs -> source-pinned Jeeves, Dragon and adversarial research challenges. This is a review milestone, **not** a trained foundation model, completed studio or autonomous screen recorder.

Canonical owners: skeleton/jeeves/game_emulator_training_lab.py performs source-bound native play, reverse replay and tabular Q updates. skeleton/jeeves/agent/lens_system.py owns the original routing lenses, and semantic_lenses, semantic_frontier, semantic_extreme_lenses, semantic_depth_lenses, semantic_research_lenses, and semantic_plane_lenses own the larger semantic catalogs. skeleton/jeeves/game_emulator_lens_review.py is a deterministic read-only projection; skeleton/jeeves/game_learning_cli.py is the existing operator boundary. It creates no new runtime, provider, storage authority, emulator or model weights.

## A. Generate actual native evidence

On a host with an operator-owned, training-rights-cleared, original compatible Game Boy ROM:

~~~sh
python -m skeleton.jeeves.game_learning_cli train-emulator-deep \
  --target game_boy \
  --rom /private/original/game.gb \
  --episode-steps 24 --max-runs 48 --stagnation-runs 10 \
  --rights-acknowledged \
  --policy-file /private/study/gb-policy.json \
  --evidence-file /private/study/gb-evidence.json \
  --checkpoint-file /private/study/gb-checkpoint.json
~~~

Use an approved installed libretro core for other compatible targets. Git checkout does not supply rights, ROM collections, firmware, native cores, or model checkpoints. Training occurs only in the emulator learning lab; the review performs no gradients, game-success detection or model promotion.

## B. Review every available lens

~~~sh
python -m skeleton.jeeves.game_learning_cli review-emulator-lenses \
  --policy-file /private/study/gb-policy.json \
  --evidence-file /private/study/gb-evidence.json \
  --lens-review-file /private/study/gb-lens-review-0.json \
  --offset 0 --limit 512
~~~

The CLI emits a short status message and writes the complete private review to a create-only file. Advance the returned next_offset using new filenames until it is null. The lens count is determined from the actual existing registries, not fixed at 43 or 200. Every routing lens gets a prefixed routing/<lens_id> key; all existing semantic lens keys retain their native IDs. Never concatenate pages with different catalog_digest or source_report_digest values.

The command reads **both** the original training policy and evidence exports, checks the split-file evidence hash, rejoins the canonical report, validates its report digest and every run receipt, requires explicit operator rights acknowledgement and all replay scrutiny checks, disallows duplicate trace identities, and checks source native-step and Q-update totals. Each lens is bound to actual run receipt fingerprints, required independent runs, Jeeves playback questions, a Dragon observation request, an adversarial falsifier, and an unproven prediction.

## C. What each lane actually establishes

| Lane | This milestone | Not yet established |
| --- | --- | --- |
| Jeeves emulator | Source-report structure and replay-receipt links | Independent core/ROM/native replay in this review |
| Dragon | Distinct lens-by-lens observation requests | Consent-scoped actual window/video capture and verified witness receipts |
| Adversarial | Source-linked counterexample tasks | Executed independent probes, falsifications and signed outcomes |
| Weights | Zero neural updates in review | Verified checkpoint access, real optimizer steps and independent holdout promotion |
| Full games | No claim of full playthrough | Terminal gameplay coverage, recovery and months-long production qualification |

A SHA-256 digest does **not** authenticate a supplied report. The output explicitly says operator_report_authenticated=false and native_runtime_reexecuted=false. A user could forge a complete report and its unkeyed digest; the source must still be verified independently before promotion. Interpretations and challenges do not become evidence merely by repetition or triangulation. Holdout episodes remain excluded from adaptive training.

## D. Continuation, failures and rollback

1. Retain private source policy, evidence, checkpoint and review pages with exact source commit/catalog digest.
2. A review invocation processes up to 512 lenses and never initiates ROM I/O, providers, model calls, autonomous screen capture or background loops.
3. After a failure, rerun unchanged inputs to a new path and compare review_digest. Existing review outputs are never overwritten.
4. Start new review pages when the training source or lens catalog changes. Do not mix generations.
5. Only the canonical future Dragon and adversarial execution owners may provide independent lane completion evidence. This projection cannot manufacture them.
6. Cancel, deadline, resource and iteration bounds stay enforced by the existing training environment. This review does not treat an exhausted budget as learning saturation.

## E. Regression and construction acceptance

~~~sh
python -m pytest -q skeleton/testing/test_jeeves_emulator_full_lens_review.py
python -m pytest -q skeleton/testing/test_game_emulator_training_lab.py
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
~~~

**L00–L13:** This is an extension under existing Jeeves game-learning ownership. It uses established admission and source rights, a versioned contract, bounded read-only operation, source lineage and fail-closed integrity checks, no new authoritative durable state, privacy-safe metadata output, deterministic recovery by replaying a pinned source, output-page limits and create-only file permissions, adversarial regression tests and explicit operator controls. A rollback removes the review command without changing existing native training artifacts or promoted models. Enterprise/game-studio release remains unqualified until the separate validators, real native games, Dragon capture and independent checkpoint training pass.

### All-page catalog completion audit

To confirm that **every registered lens** received a source-pinned review
task, collect successive results from
`review_verified_training_report(report, offset=offset, limit=512)`,
following `next_offset` until it is null. Call
`audit_lens_campaign(pages)` from
`skeleton.jeeves.game_emulator_lens_campaign`. The auditor checks page
digests, fixed source-report identity, the current complete catalog, exact
lens ordering, page boundaries, review identifiers and still-open Dragon and
adversarial lanes. Missing, duplicated, altered or prematurely promoted
pages fail closed. Its `full_registered_catalog_covered` flag is a
**review-task-coverage** result, never proof of native emulator replay,
independent Dragon watching, adversarial execution, gradient updates or
game completion.
