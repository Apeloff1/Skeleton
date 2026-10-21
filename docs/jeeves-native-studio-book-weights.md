# Jeeves: native studio interaction and complete-book candidate weights

This is an incremental integration of Jeeves' **existing** local model,
canonical creator command surface, durable runbook executor, studio frontend,
and checkpoint-derived training system. It is not a parallel AI, a hosted
model substitute, an automatic permission grant, or a declaration that an
unseen game/weight checkpoint has been trained.

## Standalone inference and editor control

`skeleton.jeeves.ai.studio_native_model.NativeStudioModel` consumes the
**already instantiated** `LocalInferenceEngine` with a
`native_transformer` checkpoint. It validates the pinned model identity
before and after generation and rejects reference-only, credential-dependent,
or unsupported models for this production-studio path.

The model receives scoped questionnaire answers and rights-declared media
*references*, produces a versioned structured proposal, and passes the
proposed creator commands through the existing
`skeleton.forge.creator.command_surface`. Real commands go through
`CreatorRunbookRunner` and an **independently issued** high-impact
`ToolGrant`. The caller/host must own the authorization decision and
provide the registered creator handler. No grant or actual side effect can
be obtained merely by inserting a tool-looking string into a prompt.

`StudioEvidenceJournal` is a transactionally appended, project/session-bound
SQLite chain. It records questionnaire answers, multimodal source identity,
native model inference, plan compilation, human approval and actual execution
outcomes. Each event hashes its canonical body and previous event hash.
The execution outcome recording method reads the matching **host-persisted**
`CreatorRunbookStore`, verifies its revision chain, and never accepts a
client-written `succeeded` flag.

### Using the controller inside a host runtime

```python
from pathlib import Path
from skeleton.jeeves.ai.studio_interaction_contract import (
    StudioEvidenceJournal, JeevesStudioController,
)
from skeleton.jeeves.ai.studio_native_model import NativeStudioModel
from skeleton.jeeves.ai.creator_runbook_store import CreatorRunbookStore

journal = StudioEvidenceJournal(
    Path("/private/jeeves/project-events.sqlite"),
    project_id="my-game", session_id="studio-session",
)
controller = JeevesStudioController(journal)
controller.answer("world", "A layered original archipelago", actor_id="operator")

# local_engine is the *real loaded* LocalInferenceEngine from the app.
proposal = NativeStudioModel(local_engine).plan(
    controller, instruction="Draft an original multi-region adventure game",
)
# A human reviews all typed operation payloads.
controller.approve(proposal, reviewer_id="authorized-operator")

with CreatorRunbookStore(
    Path("/private/jeeves/project-runbook.sqlite"),
    plan_sha256=proposal["plan_sha256"],
) as store:
    # executor is the host ToolExecutor configured with creator handlers.
    runner = controller.runner(proposal, executor=executor, store=store)
    # A host-approved EXACT ToolGrant and ToolExecutionContext are required:
    # runner.execute_step("step-000", context=context, grant=grant)
    # controller.observe(runner=runner, store=store, step_id="step-000")
```

Jeeves Chat now exposes **38 named game-production facets** and
questionnaire/forge/flow/inspect/automation modes, with per-facet questionnaire
answers kept while the palette is mounted. Its editor button navigates
into existing real app studios. The operator can also select an existing real
game-learning project and explicitly create a **plan-only** goal through
`getLearningProject` + `createStudioGoal`. The goal service returns the
actual persisted `goal_id` and status; the user may open the real Game Learning
studio to inspect goal history and receipts. This plan-only action sets
`allowEdits=false`, `maxJobs=0` and does not grant execution authority.
A prepared chat turn remains a proposal, **not** an executed editor action. Canonical chat remains text-only; images,
audio, video and engine assets require the separate existing media/crawler and
editor ingestion path. References alone do not decode or train on an image.

## Full-book admission to the candidate training pipeline

No copyrighted book text or weight checkpoint is committed to GitHub by this
change. An operator must supply book files that are owned, licensed *for
training*, or actually public domain in the relevant jurisdiction; verify the
rights assertion independently; and review the content for quality. Metadata
is not a legal clearance mechanism.

Provide a UTF-8 manifest and one `.txt` file per chapter alongside it.
All chapter files require an **independently pinned SHA-256** and affirmative
human quality review. Example:

```json
{
  "schema_version": "skeleton.jeeves.book_weights_intake.v1",
  "books": [{
    "id": "original-design-volume-one",
    "title": "Original Game Design Handbook",
    "rights": {
      "schema_version": "skeleton.jeeves.game_corpus_rights.v1",
      "source_kind": "original_authoring",
      "training_permitted": true,
      "rights_holder": "Original Author",
      "rights_basis": "original written work cleared for training",
      "review_id": "human-rights-review-01"
    },
    "chapters": [{
      "id": "chapter-one",
      "file": "chapter-one.txt",
      "sha256": "REPLACE_WITH_ACTUAL_SHA256",
      "family": "narrative",
      "quality_approved": true,
      "quality_reviewer_id": "human-editor",
      "quality_review_note": "This chapter has been independently reviewed for source quality."
    }]
  }]
}
```

The `family` must be one of the **existing** eight curriculum domains:
`mechanics`, `narrative`, `npc`, `world`, `economy`, `tooling`,
`accessibility`, `review`.

After preparing absolute directories:

```bash
python -m skeleton.ai.training.book_learning_bridge \
  --manifest /private/books/approved.json \
  --output-dir /private/books/admitted \
  --operator-review-id legal-review-01
```

This step hashes all input bytes, chunks every chapter without discarding a
short final chunk, preserves source character ordering, and creates numbered
reviewed-intake JSONL shards with hash-linked admission receipts. It creates
**neither weights nor a production promotion**.

Assemble the admitted records and independent **non-book** evaluation source
projects into the already supported
`skeleton.jeeves.game_corpus_manifest.v1` using
`jeeves_game_corpus_builder` and the human-reviewed corpus workflow. Every
admitted book segment must remain in the TRAIN split; held-out content must
come from independent projects. The current trainer imposes finite size,
word-count, and evaluation limits. The full-book runner refuses partial
coverage rather than silently claim that a large library was all trained in
one pass. For larger libraries, operators must stage separate rights-reviewed
candidate rounds with explicit checkpoint/promotion decisions.

Then, on the actual local machine that holds a loaded, trainable Jeeves
checkpoint and has the production trainer dependencies installed:

```bash
# SKELETON_OWN is the authoritative existing serving-checkpoint location.
python -m skeleton.ai.training.book_weight_candidate \
  --admission-receipt /private/books/admitted/jeeves-books-legal-review-01-receipts.json \
  --data-directory /private/books/admitted \
  --dataset-manifest /private/corpus/book-train-manifest.json \
  --expected-checkpoint-sha256 ACTUAL_LIVE_CHECKPOINT_SHA256 \
  --candidate /private/candidates/jeeves-book-candidate.json \
  --report /private/candidates/jeeves-book-evaluation.json
```

The final runner verifies all admitted shards and exact TRAIN membership,
then calls the **existing** `jeeves_production_game_train.train` optimizer
on the actual selected Jeeves weights. It emits a candidate and evaluation
report, **not** an automatic active weight replacement. Mastery, reasoning,
nonverbatim output, source attribution, regression and broad game-production
ability still need separate independent validation before any promotion.

## Supported facet families

The cockpit supports: game vision, platforms, engines, project scope, canon,
worlds, maps, pathing, narrative, dialogue, characters, NPCs, quests, combat,
movement, physics, weather, economy, inventory, progression, puzzles,
multiplayer, accessibility, localization, UI, UX, sprites, assets, scenes,
animation, audio, lighting, cinematics, playtests, QA, training, delegation
and release.

## Evidence standards

1. **Intent**: user instruction and reviewed questionnaire, scoped to a
   project/session, with media source identity and rights scope.
2. **Model**: local model SHA-256, observed inference token accounting,
   result digest and runtime receipt (when supplied by the inference engine).
3. **Plan**: validated command payloads, dependencies, content-addressed
   plan SHA-256, no execution authority in model output.
4. **Authorization**: human approval logged; separate exact host-created tool
   grants are mandatory for high-impact effects.
5. **Effect**: durable in-flight record before execution; successful outcomes
   require the actual typed creator receipt. Unknown outcomes are quarantined,
   never retried without separate reconciliation.
6. **Audit**: project/session hash chain and full host runbook state verification.

Tests are in `skeleton/testing/test_jeeves_native_studio_books.py`.
