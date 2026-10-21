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
  --report /private/candidates/jeeves-book-evaluation.json \
  --receipt /private/candidates/jeeves-book-admission-to-weights-receipt.json
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

## Additional implementation: real studio execution and reviewed multimodal inputs

The Jeeves chat cockpit now uses the **existing authenticated studio-goal client**
to create either plan-only goals or explicitly authorized **run-mode** goals
for a selected existing project. Run mode is opt-in: the user must separately
allow project edits and acknowledge effects before creating the goal. Every
action still passes through the canonical server's authorization, project
revision controls, budgets and observed runner status. The interface offers
manual bounded advancement (two steps) and an authoritative goal reload;
timeouts never trigger an automatic repeat of possibly non-idempotent effects.

The cockpit exposes server-provided goal status, revision, step and model/job
counts, integrity state, available history/state SHA-256 digests, and the actual
last-step record. A created goal, UI acknowledgement or SHA string by itself
is not proof that the complete game has shipped or that native playback occurred.

### Structured studio production flows

`frontend/src/features/Jeeves/JeevesStudioFlows.ts` defines thirteen reusable
workflows across original game production, narrative, world, gameplay, assets,
sound, physics, platform/SDK support, simulation, multiplayer, accessibility,
local AI learning and release. They use the canonical 38 facets rather than
creating duplicate forges. Longer workflows are presented in six-facet
production slices; the user's scoped answers travel into Jeeves' real studio
goal planner, and remaining stages are explicitly outstanding. A previous
goal's *verified* state digest may be recorded as a continuity reference,
but the next goal must independently verify current project state and history.

### Byte-verified multimodal augmentation

`skeleton.jeeves.ai.studio_multimodal_intake.admit_reviewed_media` can accept
real files in an approved local directory. The caller supplies an independently
pinned SHA-256, stable source ID, modality and declared rights scope. The host
checks the byte identity, source signature for selected formats, non-symlink
path, file size and project/session journal integrity. A licensed, original
or public-domain source can additionally supply a **separately reviewed**
UTF-8 sidecar generated by an installed decoder, OCR engine, transcript tool,
human annotator or media pipeline. The sidecar has its own SHA-256, decoder
identity and named independent reviewer.

Example (from the trusted application host, **not** a model prompt):

```python
from hashlib import sha256
from pathlib import Path
from skeleton.jeeves.ai.studio_multimodal_intake import admit_reviewed_media

root = Path("/private/authorized/game-media")
source_digest = sha256((root / "scene.wav").read_bytes()).hexdigest()
review_digest = sha256((root / "scene-review.txt").read_bytes()).hexdigest()

receipt = admit_reviewed_media(
    controller, root=root, file_name="scene.wav",
    expected_sha256=source_digest, source_id="scene-audio-01",
    modality="audio", rights_scope="original",
    sidecar_name="scene-review.txt", sidecar_sha256=review_digest,
    decoder_id="local-audio-reviewer-v1", reviewer_id="human-reviewer",
)
```

The previously installed studio journal gains a
`modality_observation_reviewed` event containing source SHA, observation SHA,
reviewer and decoder IDs. NativeStudioModel now selects a bounded number of
reviewed observations and records how many were available versus used. It
does **not** treat bare media IDs as visual content, claim unretrieved frames,
upload a file to a hosted provider, or train on unapproved multimodal material.

The evidence chain must be checked on the actual operator host before accepting
a result. Sidecar reviews establish who approved the description and which
bytes were provided; they are not proof of the description's accuracy.

### Verification and deployment boundaries

- Source regression suite: `skeleton/testing/test_jeeves_studio_multimodal_intake.py`.
- All actual book material and the serving native model checkpoint must be
  explicitly provided by the authorized owner; code alone cannot train the
  full books or publish new model weights.
- The real creation handlers, renderer/engine, media decoder and project
  authority must exist before a production flow can perform its intended
  effects. Unsupported forge targets must remain unexecuted, not invented.
- Production release still requires exact-source and native engine evidence,
  measured quality, independently reviewed rights and explicit promotion.

### Candidate training final provenance

After the actual existing optimizer returns and publishes its files, the
book-training bridge independently hashes the **candidate checkpoint bytes**
and the **evaluation report bytes** as well as the exact approved train,
holdout, manifest, book admission and serving checkpoint hashes. The new v2
receipt also distinguishes an actual optimizer artifact from a completed,
deployed or release-qualified Jeeves model. `--receipt` exclusively creates
one private audit file and refuses to overwrite any prior output. This does
not weaken the existing separate candidate evaluation and promotion process.

## Operational: local books used by the speaking Jeeves model

The rights-reviewed full-book curriculum now has TWO distinct usable
paths. The original `book_weight_candidate` runs real checkpoint-derived
candidate training when actual approved texts and a trainable active Jeeves
checkpoint are present. Separately, the new
`skeleton.jeeves.ai.studio_book_memory.ReviewedBookMemory` creates a private
FTS5-backed local knowledge memory from exactly those admitted shards, without
waiting for optimizer training. This is grounded retrieval augmentation, **not**
a substitute for changed model weights. Neither path uses a hosted provider.

Build and independently pin the exact original book admission receipt:

```bash
sha256sum /private/books/admitted/jeeves-books-legal-review-01-receipts.json

python -m skeleton.jeeves.ai.studio_book_memory build \
  --index /private/jeeves/book-index.sqlite \
  --project-id my-game \
  --admission-sha256 INDEPENDENT_RECEIPT_FILE_SHA256 \
  --admission-receipt /private/books/admitted/jeeves-books-legal-review-01-receipts.json \
  --admitted-dir /private/books/admitted

python -m skeleton.jeeves.ai.studio_book_memory search \
  --index /private/jeeves/book-index.sqlite \
  --project-id my-game \
  --admission-sha256 INDEPENDENT_RECEIPT_FILE_SHA256 \
  --source-root-sha256 INDEPENDENT_INDEX_SOURCE_ROOT_SHA256 \
  --query "How should alternate quests preserve world canon?" \
  --actor-id game-designer

python -m skeleton.jeeves.ai.studio_book_memory verify \
  --index /private/jeeves/book-index.sqlite \
  --project-id my-game \
  --admission-sha256 INDEPENDENT_RECEIPT_FILE_SHA256 \
  --source-root-sha256 INDEPENDENT_INDEX_SOURCE_ROOT_SHA256
```

Retain the `source_root_sha256` value from the **build** JSON response outside
this SQLite database. It is a second independent immutable binding against
coordinated rewrites of source rows and database metadata. Each subsequent
search, verification, revocation, and native-session load requires that pin.

When a source must stop being used:

```bash
python -m skeleton.jeeves.ai.studio_book_memory revoke \
  --index /private/jeeves/book-index.sqlite \
  --project-id my-game \
  --admission-sha256 INDEPENDENT_RECEIPT_FILE_SHA256 \
  --source-root-sha256 INDEPENDENT_INDEX_SOURCE_ROOT_SHA256 \
  --book-id original-design-volume-one \
  --reviewer-id authorized-human-reviewer \
  --reason "The original rights holder has withdrawn inference permission"
```

Retrieval verifies project and pinned source, uses literal non-executable FTS
query terms, bounds excerpts, excludes withdrawn volumes and chains each
result to a host-persisted search receipt. Explicit withdrawal prevents future
searches but does **not** erase the original private source file; the owner
must separately execute lawful retention or erasure policies. Trained
checkpoints already exposed to a withdrawn source require a separate model
governance decision; removal from retrieval cannot reverse training.

## Operational: standalone host session and real delegation

The application host can construct one `NativeStudioHost` around the
**already running local** `LocalInferenceEngine` and an approved project.
An operator supplies an installed native checkpoint, private working paths and
previously built book memory:

```python
from pathlib import Path
from skeleton.jeeves.ai.studio_host_bootstrap import NativeStudioHost

# engine = host's ACTUAL loaded local inference engine.
with NativeStudioHost(
    engine, project_id="my-game", session_id="session-001",
    journal_path=Path("/private/jeeves/studio-events.sqlite"),
    runbook_directory=Path("/private/jeeves/runbooks"),
    book_index=Path("/private/jeeves/book-index.sqlite"),
    book_admission_sha256="INDEPENDENT_RECEIPT_FILE_SHA256",
    book_source_root_sha256="INDEPENDENT_INDEX_SOURCE_ROOT_SHA256",
) as studio:
    studio.answer(
        "world", "Author an original multi-island world with optional routes",
        actor_id="human-producer",
    )
    plan = studio.plan(
        "Implement original quest structure, consistent cast and sky islands"
    )
    approval_receipt = studio.approve(
        plan, reviewer_id="human-producer",
    )
    # These objects MUST be provided by trusted application ownership:
    # executor = actual ToolExecutor with registered creator handlers
    # grants = {step_id: (host_execution_context, fresh_exact_ToolGrant)}
    # result = studio.execute_authorized(
    #     plan, executor=executor, host_grants=grants, max_steps=8
    # )
    audit = studio.audit()
```

The real host path now composes the existing local model and typed creator
command contract, 38 game facets, reviewed media and indexed books, durable
model/plan approval history, host-bound ToolExecutor delegation and one-shot
runbook stores. `execute_authorized` never manufactures permissions.
`studio_delegate_executor.execute_approved_studio_batch` can process
dependency-ordered authorized actions, link each successful step to its
actual persisted host command receipt, and quarantine ambiguous effects as
`in_doubt` requiring independent reconciliation. Restarting with the same
plan and project reopens the existing plan-specific SQLite execution chain.
The output's `all_runbook_steps_succeeded` is only evidence that scoped
commands finished; it does not certify full-game playthrough or release.

Additional regressions:
`test_jeeves_studio_book_memory.py` and
`test_jeeves_studio_delegate_executor.py`.

### Capability readiness

The native studio planning path requires a genuine loaded model, not merely
a reference-language-model fallback. Not all game engines, SDKs or editor
handlers are already installed. If an existing command's runtime handler is
missing, the goal remains blocked or in doubt instead of pretending that the
forge changed source files. The host must explicitly attach actual creator
handlers, target engine, media decoders, checkpoints, resources and the approved
reviewed book library before executing the corresponding production work.
