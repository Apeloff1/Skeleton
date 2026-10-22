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


## Verified project canon across months-long game production

The new `skeleton.jeeves.ai.studio_canon_memory.StudioCanonStore` is a real
SQLite-backed continuity memory: original NPC identities, regions, game-world
rules, timelines, quest outcomes, dialogue dependencies and endings can be
represented as named facts with reviewed revision history. This is persistent
working game-canon data, not language-model weights.

```python
from pathlib import Path
from skeleton.jeeves.ai.studio_canon_memory import StudioCanonStore

with StudioCanonStore(
    Path("/private/jeeves/project-canon.sqlite"),
    project_id="my-game",
) as canon:
    receipt = canon.revise(
        subject_id="captain-sera",
        attribute_id="origin",
        action="establish",
        expected_fact_sha256=None,  # establish only when fact is absent
        actor_id="authenticated-narrative-author",
        reviewer_id="independent-human-producer",
        source_receipt_sha256="e" * 64,  # replace with real source receipt!
        fact={
            "statement": "Captain Sera grew up on the northern sky islands.",
            "scopes": ["cast", "story", "world"],
            "anchors": ["sera", "sky_islands"],
        },
    )
    current = canon.get("captain-sera", "origin")
    refs = canon.search("Sera on the northern sky islands", limit=8)
    history = canon.verify()
```

Amendment is never an unscoped overwrite: it requires
`action="amend"`, the *exact* currently stored `revision_sha256`, a
separate reviewer and a fresh source-receipt binding. Retirement is similarly
explicit; an audit history remains. All revisions form a deterministic
SHA-256 chain across app restarts; startup optionally pins a separately
retained `expected_head_sha256` for independent attestation. The embedding
host must authenticate actor/reviewer identities and actually verify
external source receipts; passing an invented SHA string is NOT source review.

Enable this for a native session using
`NativeStudioHost(..., canon_index=Path("/private/jeeves/project-canon.sqlite"),
canon_expected_head_sha256=PREVIOUSLY_SIGNED_HEAD)`. The optional canonical
store starts empty when genuinely new. `studio.revise_canon(...)` exposes
authenticated host-owned changes; `studio.plan(...)` includes only relevant
source-revision-pinned reviewed canon facts in Jeeves' actual native context.
Its inference result is rejected if any project canon revision or source-book
withdrawal occurred while local inference was running, requiring a fresh
deliberation rather than stale action approval. The studio journal records
`canon_context_retrieved` and `book_memory_retrieved` as evidence separate
from the actual source-maintenance journals.

This is an implementation of persistent original game-story continuity,
not a claim that every possible plot inconsistency has been detected.
`skeleton/testing/test_jeeves_studio_canon_memory.py` contains 11 regression
cases for mutation authority, optimistic concurrency, restart/replay, source
identity, cross-project safety, and retirement.


## Operational: actual creator source files, not just planning gates

`skeleton.jeeves.ai.studio_creator_source.CreatorProjectSourceStore` is an
original-game source authoring backend with genuine SQLite writes and a
replayable SHA-linked edit journal. It is an optional host-owned source plane
for `NativeStudioHost`:

```python
from pathlib import Path
from skeleton.jeeves.agent.tools import ToolRegistry, ToolExecutor
from skeleton.jeeves.ai.studio_host_bootstrap import NativeStudioHost

# engine: the actual loaded native transformer inference engine
# The operator must create these private directories beforehand.
with NativeStudioHost(
    engine, project_id="original-game", session_id="authorized-session",
    journal_path=Path("/private/jeeves/evidence.sqlite"),
    runbook_directory=Path("/private/jeeves/runbooks"),
    source_index=Path("/private/jeeves/game-sources.sqlite"),
    source_export_root=Path("/private/jeeves/exports"),
) as jeeves:
    registry = ToolRegistry()

    # This must call the REAL application permission owner. It cannot return
    # True by default or let the model approve its own commands.
    jeeves.register_native_creator_tools(
        registry,
        authorize=host_check_authenticated_exact_creator_command,
    )
    executor = ToolExecutor(registry)

    # Actual model generation proposes a native type-checked creator plan.
    plan = jeeves.plan(
        "Author one original 2D world and three alternative paths."
    )
    jeeves.approve(plan, reviewer_id="independent-human-producer")

    # The authenticated application, NOT Jeeves, issues fresh per-step
    # ToolExecutionContext and ToolGrant for the exact creator command.
    # grants = {"step-000": (context, exact_one_shot_high_impact_grant)}
    # execution = jeeves.execute_authorized(
    #     plan, executor=executor, host_grants=grants, max_steps=8
    # )
    snapshot = jeeves.audit()
```

The source owner implements actual `CreatorCommand` operations:

- `create`: an `intent` object with exactly `record_id`, `facet`,
  `document`, and `depends_on`. Saves new original game content into the
  project SQLite database.
- `edit`: `target_id`, exact `expected_revision`, and
  `patch={"set": {...}, "remove": [...]}`. Commits only if the current
  revision and source identity match.
- `test`: reviews exact source scopes and verifies the dependency graph,
  without falsely claiming an engine playthrough.
- `preview`: returns the real selected documents in `static` mode.
  `runtime` preview fails closed without a real engine adapter.
- `export`: emits `game-source-json`, an immutable content-addressed
  source bundle. No arbitrary filesystem path is allowed inside
  `artifact_name`. Exporting source is not generating a runnable binary.

### Real Frontier Studio compiler integration

The `frontier-studio-json` export uses the existing
`skeleton.forge.game_frontier_studio.StudioProject` and
`compile_studio_project` to compile actual authored settings, tile maps,
prefabs/sprite references, 3D placements, RPG events and native quest graphs.
It is not a duplicate engine or a pretend asset generator.

For example, two source records admitted via `create` can be:

```json
{
  "record_id": "game-settings",
  "facet": "engine",
  "document": {
    "kind": "studio_settings",
    "target_era": "sprite",
    "projection": "top_down",
    "world_family": "original"
  },
  "depends_on": []
}
```

```json
{
  "record_id": "island-map",
  "facet": "map",
  "document": {
    "kind": "map_layer",
    "layer_id": "main",
    "width": 2,
    "height": 2,
    "palette": ["sky", "terrain"],
    "data": [0, 1, 1, 0]
  },
  "depends_on": ["game-settings"]
}
```

The compiler refuses to invent missing project settings, map layers,
unregistered prefab assets or invalid quest transitions. Unsupported
record kinds such as longform narrative outlines remain in the source bundle,
and `non_compilable_record_ids` explicitly reports that those sources
have **not** entered the typed Forge project.

The native model now searches existing original game records (including their
revision numbers, typed facets, dependencies and SHA digests) before
proposing edits. The model's plan is tied to a host-only
`plan_context_bound` evidence event containing the exact local checkpoint,
rights-policy, book-admission, canon and original source generations.
`execute_authorized` checks this evidence before dispatch and between
consecutive real effects. When resuming, it accepts source revisions resulting
*only* from the same verified, previously successful runbook commands.
External source changes or book-rights/canon revisions require a fresh model
proposal and review; they never trigger an automatic replay.

New regressions are in
`skeleton/testing/test_jeeves_studio_creator_source.py` and
`skeleton/testing/test_jeeves_studio_frontier_source_compile.py`.
This implementation is a real persistent game-design source compiler and
controlled workflow, not proof of live Godot gameplay, final art/audio,
complete playable world production or an installed native checkpoint.


## Runnable original Godot 4 source and genuine native playthrough path

The source compiler additionally supports a host-authorized
`export(format="frontier-godot4-zip")`. This executes the repository's
existing `author_studio_expedition`, original route simulation,
`emit_expedition_godot_project`, and
`verify_expedition_godot_project` rather than emitting a dummy image
or synthetic engine-completion receipt. It builds real `project.godot`,
`.tscn`, `.gd`, `expedition.json` and the host-authored traveler
profile and bundles them into a deterministic content-addressed ZIP.

Two **actual saved creator records** are required in addition to typed
project settings and a map layer. The `world` facet supplies an
`expedition_profile` with explicit seed, islands, spacing_m, rise_m,
branch_factor, caverns, include_underwater and include_portals. The
`movement` or `cast` facet supplies a `traveler_profile` with
permitted_modes, flags, equipment, max_stamina, carried_kg, capacity_kg,
skill and shelter. The user/host must author those settings. Jeeves does
not get undisclosed movement permissions.

The exporter exercises a real Python game route under exactly these
authored traveler constraints, then verifies that every generated Godot
file matches the existing deterministic native compiler. It writes a
`jeeves_source_receipt.json` containing the reviewed source head,
compiled/noncompiled facet coverage, world SHA, route evidence and per-file
hashes. A separate **post-fsync disk verifier** rereads the actual ZIP,
rejects unknown/unsafe ZIP entries, duplicate paths, forged ownership,
source/hash discrepancies and unbounded expansion, and returns
`disk_verification` evidence.

**Real Godot execution is a distinct privileged host operation:**

```python
# The host must authenticate the actor and independently authorize
# this exact Godot binary. This does not grant shell execution to Jeeves.
result = studio.verify_real_native_gameplay(
    godot_executable="/usr/bin/godot4",
    actor_id="authenticated-human-producer",
    authorize_native_execution=host_check_native_engine_authority,
    timeout_seconds=90,
)
```

This method calls the existing
`skeleton.jeeves.game_frontier_expedition_native_runner.run_headless_expedition`
to launch an **installed Godot 4 executable**, capture actual engine output,
and independently replay gameplay observations against the canonical Python
ExpeditionEpisode. A native receipt is journaled only if the executable ran,
the gameplay agrees, the full route completed, and no other source editor
changed the game mid-run. A missing binary, declined permission, engine
failure or mismatched result fails closed. No native engine was launched by
adding these source files; the code has to run inside an installed host.

Regressions for real project files, deterministic reexport, content
tampering, profile/capability denial, owner binding and engine execution
permission appear in `test_jeeves_studio_frontier_source_compile.py`.


## Original pixel sprite, animation and native art-resource production

Jeeves' local creator source can now produce **real lossless PNG sprite-sheet
files** using `skeleton.jeeves.ai.studio_sprite_forge`. The independent
`create` permission boundary remains unchanged. A proposed pixel-art asset
is a `sprite_forge` source record with an explicitly authored
`document.kind="pixel_sprite"` and eight required fields:

```json
{
  "kind": "pixel_sprite",
  "asset_id": "original-hero",
  "width": 2,
  "height": 2,
  "pixel_scale": 2,
  "palette": ["#00000000", "#fb764aff"],
  "frames": [
    {"frame_id": "idle-a", "duration_ms": 120, "pixels": [0, 1, 1, 0]},
    {"frame_id": "idle-b", "duration_ms": 160, "pixels": [1, 0, 0, 1]}
  ],
  "animations": [
    {"name": "idle", "frame_ids": ["idle-a", "idle-b"], "loop": true}
  ]
}
```

The real PNG compiler expands frame pixel indices against the complete,
explicit RGBA palette, scales pixels by the declared integer factor,
assembles horizontal animation frames and emits deterministic PNG chunks
with CRCs. It independently decodes and hashes the resulting RGBA image
and records each frame rectangle, duration, source revision and animation
loop. Missing pixels, invalid colors, duplicate frame IDs, undeclared
animations, invalid palette indexes and excessive image budgets fail
closed rather than inventing content.

`export(format="sprite-atlas-zip")` writes versioned, SHA-addressed
`sprites/<asset_id>.png` and `.json` animation-state files, plus a
full package receipt. The ZIP is built deterministically and its
published bytes are reread after fsync for an independent disk receipt.

`export(format="frontier-godot4-zip")` now also embeds original sprite
assets under `game/frontier/sprites/<asset_id>.png` with metadata. The
existing world exporter remains the source of the gameplay scripts;
sprite files are additional genuine Godot project resources, with
independently verified PNG pixels and source/animation hashes.

**Important distinction:** These assets are truly created and shipped as
native image resources, but the runtime actor meshes/sprite nodes have not
been automatically bound to them. The proofs explicitly report
`native_sprite_scene_binding_verified=false`; presence inside the ZIP
does not count as in-engine sprite rendering or a complete released game.

Dedicated tests cover PNG lossless roundtrips, timed animation states,
palette and dimension rejection, persisted/exported game source identity,
duplicate asset names, corrupt ZIP files, Godot-embedded image hashes and
invalid art refusal. `tests/test_jeeves_native_studio_real_artifacts.py`
also imports the creator/source/Forge/Godot/sprite suites into the
repository's root Python test collection, so CI checks these concrete
artifacts rather than only the original auxiliary test directory.


## Advanced sprite asset standard: authored pixels to native engine resources

The `studio_sprite_forge.py` production pipeline now also supports
`studio_sprite_geometry.py`, `studio_sprite_verify.py`,
`studio_sprite_godot_resources.py`, `studio_sprite_quality_metrics.py`
and `studio_sprite_native_import.py` as a deliberately separate
authoring/rasterization/independent-proof/engine-resource/quality/engine-test
pipeline. Source edits cannot bypass preflight: before a source record is
committed, the store validates actual pixel contents, their SQLite
content-addressed revision, the complete animation source and a generated
Godot `SpriteFrames`/preview scene.

### Explicit optional atlas design contract

The existing sprite schema still works. For high-quality sprites, add an
optional `atlas` object in the source document:

```json
{
  "columns": 4,
  "padding_px": 2,
  "extrude_edges": true,
  "power_of_two": true,
  "alpha_threshold": 16,
  "pivot_px": [8, 12]
}
```

The compiler validates every field and refuses unknown alternatives. It
packs frames into a deterministic multirow atlas with precise per-frame
UV rectangles, optional power-of-two dimensions, transparent unused
surfaces, 0–8 pixel gutters and edge-extruded padding against texture
sampling bleed. The authored frame interiors remain **bit-identical**
nearest-neighbor pixels, including straight alpha: no lossy resampling,
unreviewed AI repainting, or implicit palette substitution. Unsafe
hidden nonzero RGB in fully transparent colors is refused in extruded
mode. Sprite file names use portable ASCII identifiers, and GPU atlas
surfaces are bounded to 8,192 pixels per edge and one million pixels total.

The alpha-threshold policy creates **actual per-pixel collision masks**
(bit-packed hexadecimal source plus SHA), visible-pixel bounding boxes,
pixel occupancy counts, original unscaled RGBA hashes and scaled pivots.
The PNG is encoded as validated 8-bit RGBA; a second subsystem decodes
every pixel from the emitted PNG, reconstructs the palette, frame scale,
grid, padded/extruded regions, alpha masks and animation timings, and
requires exact output equivalence. This verifier runs both immediately
after compilation and during Godot ZIP inspection. Changing image bytes,
collision masks, gutter geometry, quality scores or frame timings is
a detectable integrity failure.

Every compiled sprite also receives a reproducible, objective
`objective_quality` report: alpha coverage, animation frame variety,
atlas utilization, unusually long holds, empty sprites and potential
texture-filtering bleed. Quality grading can help the human producer
prioritize improvements. It **does not** certify subjective artwork,
licensed originality or copyright compliance; those human review statuses
are explicitly false.

### Actual Godot resources, not just embedded PNG

Every sprite ZIP now packages `.png`, machine-readable frame/animation
metadata, a Godot 4 `.tres` file with a genuine `SpriteFrames` resource
and `AtlasTexture` frame rectangles, and a companion `.tscn` preview
scene with `AnimatedSprite2D` actually referencing that resource.
The full Godot game ZIP includes these files under
`game/frontier/sprites/`. Animation frame duration is preserved by the
resource's 10-FPS normalization (e.g., 120 ms is duration 1.2 at 10 FPS).
The independent ZIP verifier reconstructs these resources and checks
that every referenced atlas frame exists and matches its source.

To inspect asset compatibility **inside an installed Godot 4 process**,
the authenticated host may call:

```python
verified = studio.verify_real_sprite_import(
    record_id="hero-sprite-source",
    godot_executable="/usr/bin/godot4",
    actor_id="authenticated-human-producer",
    authorize_sprite_import=host_check_this_exact_sprite_binary_actor,
    timeout_seconds=90,
)
```

The native inspection runs Godot headless, loads the original sprite
preview scene, instantiates its `AnimatedSprite2D`, and checks real
`SpriteFrames` animation names, frame counts, loops, AtlasTexture sizes
and timing with bounded engine-output evidence. It writes a trusted studio
journal event **only if** a separately authorized real Godot 4 binary
actually ran, the frame/source data agreed and the project generation
did not change. It does not claim actual on-screen rendering, artistic
quality approval or that the main 3D avatar uses the sprite. The source
package has engine-binding authoring capability; in-engine verification
still depends on running Godot in an installed deployment.

New tests include the 24-case adversarial sprite-quality suite, separate
original-asset tests, and real game ZIP packaging checks. Root backend CI
imports these suites from `tests/test_jeeves_native_studio_real_artifacts.py`.
**Passing exact-head CI remains required** before calling this production
pipeline verified.


## Source-authored avatar binding to the actual Expedition player

The original sprite forge now has a **real main-game integration path**, not
only an isolated preview. After creating a `sprite_forge` source record,
create a reviewed `scene_forge` record referencing it as an explicit
dependency:

```json
{
  "kind": "sprite_actor_binding",
  "target": "player_actor",
  "asset_id": "original-hero",
  "animation": "idle",
  "pixel_size": 0.025,
  "vertical_offset_m": 1.5,
  "billboard": true,
  "hide_capsule": true
}
```

The record's `depends_on` must include the original sprite's **record ID**.
The compiler rejects unknown sprites, nonexistent animation states, competing
player bindings, arbitrary targets, unsafe resource identifiers, nonfinite or
out-of-range pixel/position scales and any undeclared fields. In particular,
the model can never contribute GDScript text; only the trusted fixed native
generator can create the actual binding.

With a valid reviewed source, `frontier-godot4-zip` patches the genuine
`game/frontier/expedition.gd` player spawn anchor. The game now creates an
`AnimatedSprite3D` from the authored `SpriteFrames` `.tres`, attaches it
to the actual moving actor node, sets its typed animation and billboard
configuration and optionally removes the original capsule mesh **without
hiding the child**. It preserves actor coordinates and the original game
routing logic. An independent verifier recreates the entire patched script
from the canonical Expedition source, checks byte equivalence, validates the
bound sprite and animation references against archived resources, and
hashes the original and rewritten script.

### Native playback must test the exact modified project

The prior headless native runner regenerated the baseline Expedition world;
a successful baseline route would **not** demonstrate that this animated
player binding loaded. To prevent false attribution, the host now selects
`studio_sprite_bound_native_runner.run_sprite_bound_native_expedition`
when an avatar is authored. This runner writes and runs the **exact
content-hashed generated files including PNGs, SpriteFrames and the modified
game script**, adds independently planned autoplay input and executes an
installed Godot 4 binary. It checks the executable hash before/after,
the engine's unique gameplay completion output, world identity and
independent per-action replay against the typed Python state machine.

`NativeStudioHost.verify_real_native_gameplay(...)` remains a separately
authorized host operation and emits evidence only after success. The result
distinguishes `native_player_avatar_script_executed` from
`native_visual_output_independently_observed=false`: a headless game run
does not prove subjective appearance, screenshot fidelity or finished art
direction. Game exports alone continue to declare
`native_sprite_scene_binding_verified=false`.

These milestones also synchronize the strict canonical AI file-tree mirrors
for all newly created Jeeves studio modules and move the owned
`runtime_learning` contracts into their required governed mirror. Existing
canonical runtime/owner modules are not deleted or rewritten to bypass a
quality gate.


## Lossless directional animations and exact collision topology

Two more concrete sprite-production steps now compile from the SAME
approved, revisioned `sprite_forge` document:

**Authored directional variants.** Add an optional `variants` list:

```json
{
  "frame_id": "hero-face-left",
  "source_frame_id": "hero-face-right",
  "transform": "flip_horizontal",
  "duration_ms": 120
}
```

The explicit transforms are `flip_horizontal`, `flip_vertical`,
`rotate_180`, `rotate_90_cw` and `rotate_90_ccw`. Quarter-turns
require square frames; otherwise the compiler rejects the operation instead
of cropping or implicitly changing the approved sprite dimensions. Each
variant references one **original** authored frame (never another variant),
has its own authored duration, is bounded by the same 64-frame limit, and may
be named in normal animation timelines or Godot player travel-mode animation
maps. Frame pixels are rearranged losslessly with no interpolation or
machine-invented artwork. The compiled sprite receipt includes signed
source- and destination-RGBA hashes and transform parameters. The independent
PNG verifier decodes the final atlas, reconstructs the original source
frames, replays every directional transform on actual RGBA pixels and refuses
an invented, retargeted, repeated or altered frame. This is a reproducible
game-art transformation, not model image generation or a claim of training.

**Pixel-exact collision topology.** The `studio_sprite_hitboxes.py` compiler
turns each frame's already reviewed alpha-threshold mask into nonoverlapping,
maximally vertical-merged source rectangles. It independently rasterizes the
whole rectangle collection, requiring **exactly one** collision hit on
every solid pixel and no hit on any clear pixel. Geometry is expressed both
in original source pixels and scaled sprite-local coordinates relative to the
authored pivot. The output includes each mask SHA, source revision identity,
frame timing, shape count and a content-addressed receipt. Per-frame and
whole-atlas budgets protect consumers against pathological masks.

Every `sprite-atlas-zip` now includes
`sprites/<asset_id>.hitboxes.json`; the Godot game ZIP similarly includes
`game/frontier/sprites/<asset_id>.hitboxes.json`. The Godot ZIP verifier
rebuilds the collision geometry from the PNG's reviewed alpha-mask evidence
and compares every rectangle and hash. The files are ready for a native
physics adapter, but **collision nodes are not yet instantiated in Godot**;
the manifest explicitly states that and does not award gameplay collision
certification.

Dedicated regression suites cover frame reflection, rotation,
non-square refusal, animation state references, forged transform receipts,
source revisions, exact sparse/opaque alpha masks, geometric reconstruction,
collision sidecar export and independent Godot package verification. These
are imported by the repository's root backend test collection.
