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


## Signed palette skins and independent saved-sprite ZIP verification

Original color skins are now an actual producer tool rather than a design
promise. Jeeves can propose a `sprite_forge` source record with
`kind: "sprite_palette_variant"`, unique portable `asset_id`,
`parent_record_id` pointing at one previously admitted `pixel_sprite`
record, and an explicit `color_map` from original `#RRGGBBAA` values
to replacement `#RRGGBBAA` values. A separate reviewed source dependency
on the parent record is mandatory. Example:

```json
{
  "kind": "sprite_palette_variant",
  "asset_id": "hero-night",
  "parent_record_id": "hero-source",
  "color_map": {"#ff0000ff": "#3366ffff"}
}
```

Authoring store creation or edit checks both the parent and palette variant
revision SHA before accepting the transaction, and rechecks all dependent
palette skins whenever source sprite frames/palettes change. A skin may
change only explicitly mapped RGB values; alpha, hitboxes, animation state,
timing, frame UV rectangles and pixel coverage are immutable. Missing palette
keys, redundant identity color maps, unrelated source dependencies, duplicate
or unsafe asset IDs and hidden RGB in transparent colors fail closed.

The compiler produces **actual separate PNG, .json, .hitboxes.json,
.tres and .tscn files** for the skin in both standalone sprite ZIP exports
and full Godot game exports. Every skin carries the immutable original source
revision, variant source revision, compiled output SHA, source PNG SHA,
and approved RGBA mapping, plus an independent pixel-by-pixel replay that
checks every original and recolored pixel (including gutters) against
the declared mapping. Neither an artist's creative approval nor use of a
generative image model is asserted.

A second, standalone `studio_sprite_zip_verify.py` verifier now rereads
every published `sprite-atlas-zip` **from disk**, validates safe ZIP paths,
metadata, exact file membership, decompression and total file budgets,
fully decoded PNG source, frame timings, objective quality receipts, collision
rectangles and animation resource identity. It also replays each recolor
against the exact saved original PNG, rather than trusting a renamed
compressed ZIP or a fresh outside hash.

CI includes 17 separate adversarial palette/source/archive tests, a
whole-game Godot palette-package roundtrip, and deep/shared DAG source
regressions. The real engine source paths are implemented; **an installed
Godot runtime, actual renderer and human creative/copyright review remain
independent gates** and are not claimed as completed by these artifacts.


## Original eight-way avatar facing follows actual Godot world movement

The real game sprite actor compiler supports an **optional original compass
animation map** on a source-authorized `scene_forge` record with
`document.kind="sprite_actor_binding"`:

```json
{
  "kind": "sprite_actor_binding",
  "target": "player_actor",
  "asset_id": "hero-idle",
  "animation": "idle",
  "pixel_size": 0.025,
  "vertical_offset_m": 1.5,
  "billboard": true,
  "hide_capsule": true,
  "directional_animations": {
    "north": "face-n",
    "north_east": "face-ne",
    "east": "face-e",
    "south_east": "face-se",
    "south": "face-s",
    "south_west": "face-sw",
    "west": "face-w",
    "north_west": "face-nw"
  }
}
```

Every named animation must already exist in the **actual** reviewed
`sprite_forge` record whose source ID is in this binding's
`depends_on` list. All eight directions are supported; subsets are
valid, but missing directions never result in guessed art. Invalid
animation names, unrecognized directions, source edits removing an
in-use animation, and competing actor sources fail before publishing
a broken world. The source editor rejects destructive dependent edits
before committing its SQLite revision.

The compiler changes the real Godot Expedition `_place_actor()` source
rather than creating an unused animation helper. After an approved
navigation edge causes an actual waypoint change, it derives horizontal
heading from the previous and new actor positions, explicitly discards
vertical-only movement, and selects an existing compass animation.
World **north** is negative Z; **east** is positive X. All source
changes are produced deterministically from a trusted engine-script
anchor and independently recompiled during ZIP verification. If a
travel-mode animation is also authored, a matching compass animation
wins after the successful waypoint transition; nonexistent headings
leave the previous mode animation unchanged.

The source receipt includes
`player_compass_godot_source_receipt` with reviewed source identity,
original and transformed GDScript hashes, coordinate conventions,
and exact authored directions. A second source verifier reconstructs
every byte before the Godot ZIP receives a disk acceptance receipt.
This is **real engine-loadable source generation**, not a claim that
Godot rendered the result.

The new `test_jeeves_studio_sprite_direction.py` contains 14
regressions for cardinal and diagonal identifiers, actual Godot source
movement, preserved stamina/navigation authority, malicious frame
references, tampered GDScript, missing source animations, and
dependency-breaking edits. These tests are imported into root Python
CI and the modules are mirrored into `skeleton/ai/agents/jeeves/ai`
without relaxing architecture parity requirements.


## Real Godot compass observations and independent route replay

In addition to compiling the eight-direction `AnimatedSprite3D` script,
the original game host now observes **actual native animation transitions**
from that script during separately approved Godot 4 route playthroughs.

A successful **native runtime** invokes the trusted game script. After an
authorized waypoint transition has moved the original actor, and only if
that compass direction was explicitly mapped to a real sprite animation,
the actor reports an engine observation containing the visited waypoint
ID, direction and chosen original animation. A navigation action blocked
by its travel/stamina/permission rules does not advance the actor and
therefore cannot produce a legitimate observed compass change.

`studio_sprite_compass_evidence.py` independently reconstructs all
expected compass observations from the **actual Python ExpeditionWorld**
and the already-reviewed autoplay edge ID sequence, using each waypoint's
original X/Y horizontal coordinates. It verifies precise waypoint
identity, event count and order, animation name, world/project route hash,
and the source-bound player-sprite receipt. An absent, duplicate,
reordered, fabricated or mismatched event refuses the native compass
attestation. A route containing no mapped directional animation produces
zero events and an explicitly false `sprite_animation_observed` flag,
rather than pretending the engine exercised a compass direction.

`run_sprite_bound_native_expedition` consumes the independent report
**only after** the real installed Godot process exits successfully and
the full gameplay replay already agrees with the Python reference.
The native execution receipt includes
`compass_replay_receipt_sha256`,
`observed_compass_transitions` and
`native_player_heading_observed`, while the host-facing receipt includes
`native_compass_route_replay_receipt_sha256`. The native code also
supports **NPC-only** sprite games without falsely dereferencing a
nonexistent player sprite receipt. Native visual observations still
**do not** certify pixel output, screenshot identity, animation quality
or final game release.

`test_jeeves_studio_sprite_compass_evidence.py` supplies 15 focused
world-geometry and replay tests; these are included in the root backend
test suite. They challenge foreign worlds, missing transitions, duplicate
events, spoofed frame names, unbound waypoints, reversed playback order,
altered source policies and malformed logs. The original native engine
execution path remains host-authorized and unavailable without a real
approved Godot 4 binary.


## Native decoded RGBA image proof and time-domain animation scrutiny

### Imported Godot 4 texture pixels (not just metadata)

The separately host-authorized `studio_sprite_native_import.py` now runs
an **actual two-stage Godot 4 import**. It prepares the original sprite
project, executes the installed engine's bounded
`--headless --editor --import` resource-import phase, then launches a
second headless GDScript inspector.

The inspector loads the genuine `AnimatedSprite2D` scene and its
`SpriteFrames` and `AtlasTexture` resources, checks every authored
animation name, ordered frame count, loop policy and frame duration,
and now compares **all four atlas coordinates** for every frame: X/Y
offset and width/height. It also loads the original RGBA PNG using the
engine's `Image.load_from_file`, insists on the actual RGBA8 format and
declared dimensions, hashes the decoded complete image's pixel buffer
using Godot `HashingContext.HASH_SHA256`, and requires that digest to
agree with the Python sprite compiler's independent
`pixel_content_sha256`. A successful native import report includes
`decoded_rgba_sha256`, actual decoded pixel-byte count, import log
SHA, native executable SHA and an explicit `visual_rendering_verified=false`
flag. A refused importer, mismatched image format, wrong pixel or
bad atlas coordinates fail closed. The approved native binary is
rehashed after both process phases to detect executable replacement.

These capabilities are **committed code paths**, not claims of native
engine execution on the GitHub-connected assistant host. An installed
Godot 4 binary and host permission are still necessary.

### Pixel-resolved temporal quality inspection

The new `studio_sprite_temporal_quality.py` recomputes each original
animation frame's RGBA contents from the authored PNG at the exact
integer pixel scale. For every frame it records original unscaled RGBA
SHA, actual opacity-weighted alpha centroid, alpha-weight sum,
number of changed RGBA pixels and changed alpha pixels relative to
the preceding frame, and the integer fixed-point centroid step.

The resulting evidence highlights transparent frames, consecutive
identical frames and potentially large registration jumps across an
animation. These are quality **review signals**, not automated
creative or subjective judgment. They are added to each sprite's
hash-linked metadata receipt and independently reconstructed by the
read-side `studio_sprite_verify.py`; arbitrarily editing the temporal
review, even while recomputing the outer receipt digest, cannot substitute
for unchanged original PNG pixels.

Twelve focused tests in
`skeleton/testing/test_jeeves_studio_sprite_temporal_quality.py`
cover unchanged and altered frames, alpha transitions, unpremultiplied
opacity, oversized or invalid geometry, jitter warnings, deterministic
rebuilds, and deliberately forged quality metadata. These tests are
included in the root CI test collector. This stage neither generates
a new sprite frame nor performs an actual on-screen rendering.


## Frame-accurate animation cues on real Godot actors

A reviewed, persistent `sprite_forge` record with
`document.kind="pixel_sprite"` may optionally include an authored
`cues` list. Each cue names an existing animation, a **zero-based
animation sequence index**, a portable event ID, and one finite signal
category. For example:

```json
{
  "cues": [
    {"animation": "walk", "frame_index": 0,
     "event_id": "step-left", "category": "footstep"},
    {"animation": "walk", "frame_index": 2,
     "event_id": "step-right", "category": "footstep"},
    {"animation": "attack", "frame_index": 3,
     "event_id": "sword-impact", "category": "impact"}
  ]
}
```

The source compiler validates these against the **actual ordered,
authored** `animations[].frame_ids`, including repeated frames in a
cycle. It refuses unknown animations, out-of-range indices, duplicate
cue IDs at the same animation frame, unsupported effect categories,
untrusted script text, explicit `null` or over-budget records. It
computes a SHA-bound canonical cue schedule and independently replays
it during PNG/animation verification. Pre-commit source validation
rejects malformed cue authorship before the SQLite game source changes.

Compilation emits real
`game/frontier/sprites/<asset_id>.cues.json` and
`game/frontier/sprites/<asset_id>.cues.gd` in the Godot game ZIP.
Standalone sprite ZIPs emit the same source files under `sprites/`.
The native GDScript extends `AnimatedSprite3D`, observes
`frame_changed` and `animation_changed`, and emits typed
`cue_fired(event_id, category, animation_name, frame_index)` signals
with no arbitrary user GDScript, host shell, filesystem, scene changes
or synthesized sound output.

An explicitly authored `sprite_actor_binding` wires that script
onto the moving **player** `AnimatedSprite3D`. An explicitly authored
`sprite_npc_binding` likewise wires it to the actual Godot NPC cast
sprite. The game compiler hashes each source and cue-resource receipt;
the independent exported ZIP verifier reconstructs the exact GDScript
and timeline. The original source dependency and animation names
remain authoritative.

**The emitted signals are live game hooks, not automatically playing
music, producing particle effects, dealing combat damage or asserting
audible/visual output.** Effects require a separate reviewed consumer.
A source-only build and a unit test are not proof that a Godot engine
has launched; native replay and the installed-engine validation remain
distinct privileged host operations.

The root CI collector now runs
`skeleton/testing/test_jeeves_studio_sprite_frame_cues.py`, including
malformed source, unsafe-event, duplicate-frame, tamper, persistence
and full Godot player/NPC packaging regressions.


## Explicit-heightfield sprite normal maps (additive production milestone)

The local pixel sprite forge now optionally accepts an original `lighting`
field with `kind="heightfield_normals"`, a reviewed `strength` (integer
1..32), and one exact `height_frames` record per compiled animation frame.
Each frame supplies its existing `frame_id` and an explicit row-major list
of 8-bit grayscale heights. A 2×2 original frame uses four values; there is
no hidden depth inference, image-model claim or invented scene geometry.

```json
{
  "lighting": {
    "kind": "heightfield_normals",
    "strength": 8,
    "height_frames": [
      {"frame_id": "idle-0", "heights": [0, 90, 140, 255]},
      {"frame_id": "idle-1", "heights": [255, 140, 90, 0]}
    ]
  }
}
```

`studio_sprite_surface.py` computes deterministic clamped central
heightfield derivatives and encodes normalized tangent-space vectors in
a real lossless RGBA PNG. It preserves the source color atlas alpha
exactly, uses the identical frame rectangle, pixel scaling, atlas padding
and gutter-extrusion policy, and refuses missing/ambiguous frame height
records, non-integer/boolean samples, or out-of-range values. It does
not recolor the original diffuse sprite.

Outputs appear as `sprites/<asset>.normal.png` in the sprite-only ZIP
and `game/frontier/sprites/<asset>.normal.png` in the Godot project ZIP.
Both packages also include `<asset>.normal.source.json` containing the
actual approved author-provided heightfield. The regular sprite receipt
binds original frame height SHA-256 hashes, the normal-map RGBA SHA,
diffuse PNG SHA, output dimensions and compilation policies. The
published Godot ZIP verifier rereads both files and independently
regenerates **every normal PNG byte from the original heightfield**, in
addition to checking tangent-vector normalization and perfect alpha
equivalence. Heightfield records are subject to normal source revision
and pre-persistence checks, so changes require a new explicit edit and
revised source hash.

There are **14 new regression cases** in
`skeleton/testing/test_jeeves_studio_sprite_surface.py`, collected into
root CI, and a game ZIP round-trip test in
`test_jeeves_studio_frontier_source_compile.py`. These cover real PNG
content, flat/upward and non-flat normals, alpha preservation, explicit
source replay, altered height pixels, invalid types/frame IDs, tampered
receipts, missing heightfield output, and actual ZIP export. The
native renderer has **not** yet been demonstrated as using these
normal maps to shade actors. The receipts explicitly distinguish
source-compiled normal textures from actual Godot lighting.


### Reviewed sprite lighting in Godot 4

The sprite compiler now emits **two distinct SpriteFrames resources** when an
original sprite has an authorized `lighting.height_frames` source:
`<asset>.tres` is the unmodified diffuse-only animation resource used by
`AnimatedSprite3D` player/NPC bindings; `<asset>.lit.tres` is a 2D-only
`CanvasTexture` resource combining the lossless diffuse and normal atlas
with identical animation rectangles. The `<asset>.tscn` preview loads the
latter and includes a `DirectionalLight2D`. Unlit sprites retain their
original two-resource layout. Neither a 3D renderer nor the 2D preview may
silently substitute one resource for the other.

Both original-game and standalone ZIP verifiers regenerate the engine text,
read and replay the actual saved normal-map PNG against the independently
approved heightfield, check alpha and SHA evidence, and reject unexpected or
missing resource members. Native import inspection additionally checks the
real loaded 2D CanvasTexture normal binding and actual decoded source RGBA,
while refusing CanvasTexture as a 3D sprite atlas. These are source/native
resource checks, **not** an assertion that framebuffer pixels were observed,
lighting quality was artistically approved, or 3D normal shading was added.
3D normal-map shading requires a separate reviewed, 3D-compatible material.

Engine compatibility: Godot 4 CanvasTexture is documented as 2D-only:
https://docs.godotengine.org/en/stable/classes/class_canvastexture.html

### October 2026 — real asset descriptors and multi-format compiler expansion

The `studio_asset_descriptors.py` module now compiles searchable, versioned,
source-owned asset descriptors for original PNG sprites, PCM WAV sounds and
parametric glTF 2.0 GLB meshes. These are actual compiled media bytes, not
declarations of nonexistent models or automatic visual understanding. Every
descriptor includes stable content SHA-256, compiler receipt, source record and
revision, media type, exact measured technical properties, applicability and
explicitly **uncertified** rendering/legal claims.

#### New original parametric 3D meshes

Create a host-authorized source record `facet=asset_forge` with
`document.kind=procedural_mesh` and exactly:

```json
{
  "kind": "procedural_mesh",
  "asset_id": "temple-pedestal",
  "primitive": "box",
  "size_mm": [1200, 700, 900],
  "segments": 12,
  "color_rgba": "#aabbccff",
  "metallic_per_mille": 100,
  "roughness_per_mille": 850
}
```

Supported primitives are box, plane, cylinder and UV sphere. Box faces
preserve hard-edged normals; ellipsoids and elliptical cylinders use
inverse-scale-corrected normals. The model produces a real glTF 2.0 GLB:
interleaving is not assumed, attributes are POSITION/NORMAL/TEXCOORD_0,
indexed triangles use unsigned 16-bit indices, PBR metallic-roughness
parameters are source-authored, and binary views are aligned. The 3D
coordinate system is Y-up and measured in meters, converted from the
integer millimeter source units. Source bounds, triangle/index counts,
separate binary SHA and full GLB hash are in the compilation receipt.
An independent GLB verifier parses all chunks and reconstructs the full
source vertex/index buffer. Triangle and byte budgets are explicit; an
oversized scene cannot be silently simplified.

The Godot export writes
`game/frontier/meshes/<asset>.glb` and
`game/frontier/meshes/<asset>.source.json`. The post-publication verifier
reconstructs actual model bytes against the archived source. Godot's importer
may consume the .glb when installed; **no installed Godot renderer/importer or
3D gameplay is certified by source export alone.** Animation/skin/complex
scene-graph authoring remain distinct later capabilities.

#### User-authored asset descriptors

Create a second **approved** `asset_forge` source with
`kind=asset_descriptor`. It must depend on the specific target source
record, use the actual compiled asset ID and provide exactly the fields below.

```json
{
  "kind": "asset_descriptor",
  "target_record_id": "temple-source",
  "target_asset_id": "temple-pedestal",
  "title": "Temple pedestal",
  "description": "Original rectangular stone pedestal for the ruins.",
  "alt_text": "Short rectangular pedestal made for a temple scene.",
  "tags": ["temple", "stone", "original"],
  "roles": ["environment", "prop"],
  "locale": "en",
  "rights_status": "self_authored_asserted",
  "attribution": ""
}
```

The source owner validates the record's revision, dependency and typed
contract **before committing** it to SQLite. Compiled assets without a human
semantic source get **structural-only** descriptors: file identities, dimensions,
palette, RGBA occupancy, exact animation timelines/holds, image-alpha bounding
rectangles, collision availability, normal-atlas reference, PCM audio amplitude,
duration and sample rate, or real triangle/vertex/PBR metrics. They do NOT get
imagined appearance, characters, dialogue or semantic roles. The rights field
records an assertion, not verified ownership; the compiler makes no copyright
clearance claim. External rights assertions require attribution.

Original sprites have diffuse-only 3D SpriteFrames resources, with separate
2D CanvasTexture normal-lit previews. Descriptors preserve that distinction.
The JSON Schema Draft 2020-12 author contracts are in
`docs/schemas/jeeves-original-mesh-2026.schema.json` and
`docs/schemas/jeeves-reviewed-asset-descriptor-2026.schema.json`.
Runtime Python validation remains authoritative and also pins the real
source revision hashes and exported content bytes. The schema does not
purport to implement an unpublished newer JSON Schema draft.

#### Search, caching, binary authority and studio use

`CreatorProjectSourceStore.compiled_asset_catalog()` compiles all supported
original assets, seals descriptors and builds a deterministic token inverted
index. The cache is scoped by the independently reread SQLite source head.
Call `search_original_assets(query, kind=None, limit=6)` to retrieve actual
descriptor records with a search-result hash. A constructed
`NativeStudioHost.search_original_assets` provides the same read-only API.
Jeeves native deliberation reads at most four relevant source-reviewed
descriptors and writes a distinct `asset_catalog_context_retrieved` journal
receipt bound to the same project source head; this confers **zero** creator
permissions or model weight updates.

Standalone sprites ship `assets/catalog.json`, while Godot ZIPs ship
`game/frontier/assets/catalog.json`. The original full-book/rights and
SQLite creator journal workflows are preserved. Catalog replay **after
archive publication** decodes original RGBA/WAV/GLB bytes, reconstructs
technical descriptors, rechecks any semantic source, and exactly reproduces
its inverted index. It refuses extra or omitted descriptors, metadata swaps,
duplicate overlays, changed source receipts and missing/foreign source
records. Palette variants are tied to their explicit source-color derivation
proofs rather than receiving guessed parent authorship.

Interoperability is via JSON Schema Draft 2020-12 plus optional glTF 2.0
`asset.extras` projection using `gltf_extras_for_asset`, not a fabricated
extension registration or claim that a 2D sprite is suddenly a 3D glTF mesh.
`SPDX 3.0` and `C2PA` are **not** emitted by this work: stored human
rights assertions and hash-linked human-authored alt text are not substitutes
for those complete credential/signing mechanisms.

References:
- https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html
- https://json-schema.org/draft/2020-12/
- https://spdx.dev/use/specifications/
- https://docs.godotengine.org/en/stable/classes/class_canvastexture.html

Validation source: `skeleton/testing/test_jeeves_studio_asset_compilers_2026.py`
and the extended native ZIP tests. Source commits are not themselves
proof of completed engine imports, 3D framebuffer images, final-game
playthrough or certified legal rights. Review the **exact-head** CI jobs
before merge.

#### Standalone descriptor-only artifact

The creator exporter also accepts `format=asset-catalog-json`, writing a
content-addressed `<artifact>-<sha>.json` containing reviewed descriptors and
real byte-derived metrics for every current original sprite, WAV and GLB.
Unlike `frontier-godot4-zip`, it does not require a completed playable
world or Godot runtime. Each export is pinned to the current Creator
SQLite source head, deterministically hashed, and refuses overwriting a
conflicting target. The source owner also exposes a read-only searchable
catalog to the authenticated studio host and the standalone Jeeves model.

### October 2026 — reviewed 3D LOD forge and instantiable GLB assets

Source-authored 3D cylinder and UV-sphere projects can now add a second
`asset_forge` record `kind=procedural_mesh_lod_set`, with
`base_record_id`, `asset_id` and an ordered `levels` array. Each level
must have `level`, `segments` (strictly decreasing) and
`switch_distance_mm` (strictly increasing). The LOD record MUST depend on
the reviewed base mesh. A mesh-source edit that invalidates its LOD chain is
refused *before* the SQL transaction. No silent decimation or silent
simplification is performed; every lower-poly asset is rebuilt deterministically
at its authored segmentation.

A real original Godot project ZIP now ships the parent `.glb`, derived
`.lodN.glb` binaries, a complete `.lods.source.json` source/lineage
package, `.tscn` importable GLB wrapper, and—when LODs exist—`.lod.gd`
plus `.lod.tscn` camera-distance instancing controller. The generated Godot
script includes a 0.25 m hysteresis buffer around authored switching
distances to avoid threshold oscillation. Independent ZIP verification
reconstructs all lowered geometry and exact GDScript/scene content, rejects
orphan executable mesh scripts, and checks both real source-record hashes and
derivation proofs.

Every derived LOD binary also receives its own indexed asset descriptor. The
descriptor includes the original parent asset identity, authored LOD source
SHA-256, original LOD set receipt, source segmentation and switch distance.
Author-reviewed descriptive meaning, alt text, tags, roles and *asserted*
rights may be inherited from the parent with
`inherited_parent_source_not_independent_vision` status. Such inheritance is
not independent image recognition, copyright clearance or actual native
render verification. Both the exported Godot catalog and standalone
`asset-catalog-json` include the derived assets; the independent catalog
verifier replays all LOD binary bytes.

Source contract: `docs/schemas/jeeves-original-mesh-lod-2026.schema.json`.
Validation: `test_jeeves_studio_mesh_lod_2026.py` and
`test_jeeves_studio_frontier_source_compile.py`. Godot import,
visible geometry and runtime LOD swapping remain unverified until
host-authorized engine execution and independent observation.

### Original 3D mesh collision and physics compilation — October 2026

Jeeves can now author *real* source-owned Godot 4 collision-body scenes for
previously compiled original 3D GLBs. This is an opt-in record under
`facet=physics`, document.kind=`procedural_mesh_physics`; the source
`depends_on` graph must include the already-approved original
`procedural_mesh` record. The exact authoring input is:

```json
{
  "kind": "procedural_mesh_physics",
  "base_record_id": "temple-source",
  "asset_id": "temple-pedestal",
  "body_type": "static",
  "density_kg_m3": 2300,
  "friction_per_mille": 850,
  "restitution_per_mille": 50,
  "collision_layer": 1,
  "collision_mask": 31
}
```

**Three actual Godot node types:** static emits `StaticBody3D`, rigid
emits `RigidBody3D` with mass derived from source dimensions and authored
density (and enabled continuous collision detection), area emits `Area3D`
with native monitoring enabled; area scenes are trigger surfaces but do not
invent a gameplay signal handler or synthetic contact events. Body geometry
is derived from the same source that emits the GLB. Boxes are `BoxShape3D`,
finite ground planes are thin 10 mm boxes, true uniform spheres are
`SphereShape3D`, circular cylinders are `CylinderShape3D`. Ellipsoids
and elliptical cylinders instead use `ConvexPolygonShape3D` with the real
unique parametric source vertices, not a physically inaccurate uniform
radius. All emitted convex polygons have explicit complexity bounds.

Static and rigid bodies receive real `PhysicsMaterial` friction and bounce;
rigid bodies derive mass from authored kg/m³ and analytic box, cylinder or
ellipsoid volume, with limits to refuse unstable or impossible mass ranges.
Collision layers and masks are bounded integers. Source mutations are
checked before the durable source-store SQLite transaction, so a later
mesh rename, physics policy invalidation or geometry change cannot
silently orphan collision assets. A base mesh without an authorized physics
record is left untouched and uncollidable by default.

**Real published artifacts:**
`game/frontier/meshes/<asset>.physics.tscn` includes the actual
body, collision shape, physical material where applicable and an instanced
rendering child pointing to the existing original GLB or authored LOD scene;
`game/frontier/meshes/<asset>.physics.source.json` retains source revision
and compiler metadata. The project receipt records source IDs, source SHA,
GLB SHA, scene SHA, collision body type and physics compilation receipt.
The separate post-publication verifier independently recreates all physics
scene/source bytes, checks that each visual is linked to the existing
reviewed GLB/LOD scene and forbids unapproved additional collision files.

**Jeeves asset search:** base mesh descriptors now include authored collider
shape, collision layer/mask, physical material, mass, type, scene SHA and
source revision; the catalog is fully replayed from real source records.
Source emission proves compiler behavior, not actual observed contact,
collision response, trigger notifications or a Godot engine run.
The physics source contract is available at
`docs/schemas/jeeves-original-mesh-physics-2026.schema.json`.

Coverage: `test_jeeves_studio_mesh_physics_2026.py` includes 24
adversarial source, geometry, deterministic emission, scene replay,
catalog and mutation tests, supplemented by 3 full source-store/native-ZIP
integration tests in
`test_jeeves_studio_frontier_source_compile.py`.
Native Godot import and runtime physics remain separate release milestones.

### Authored 3D model placement in the actual Godot game world

The original mesh and physics pipeline now has a real source-governed scene
instance compiler (`studio_original_mesh_placements.py`). This resolves the
critical difference between merely shipping separate .glb/.tscn resources and
actually instantiating assets within the playable expedition scene.

An approved `scene_forge` source with
`document.kind=original_mesh_instance` includes exactly
`instance_id`, `base_record_id`, `asset_id`, `physics_record_id`,
`position_mm`, `rotation_deg` and `scale_per_mille`.

```json
{
  "kind": "original_mesh_instance",
  "instance_id": "temple-doorway",
  "base_record_id": "temple-source",
  "asset_id": "temple-pedestal",
  "physics_record_id": "temple-physics-source",
  "position_mm": [1500, 3200, -550],
  "rotation_deg": [0, 90, 0],
  "scale_per_mille": 1000
}
```

A physical scene instance requires `depends_on` to include both the
existing mesh-source ID and reviewed physics-source ID. An uncollidable
visual-only instance requires `physics_record_id=null`. If the original
mesh has an LOD set and no attached physics, the compiler references the
authored LOD scene; when physics is enabled, it selects the actual
original physics-body scene, which in turn instantiates the authored
LOD visual geometry. Uniform scale preserves the source physical shape,
while translation/rotation are explicit integer-authored world units.

The output includes:
- `game/frontier/mesh_placements.tscn` — an actual child scene with
  explicit `PackedScene` imports and unique `Node3D` instances.
- `game/frontier/mesh_placements.source.json` — the exact reviewed source
  records, authored transform/mesh identities and a sealed compiler receipt.
- `game/frontier/expedition.tscn` — independently verified in-place
  attachment to the real `FrontierExpedition` root, retaining the original
  gameplay `expedition.gd` script. Empty placements leave the base scene
  byte-identical.

The post-publication verifier reruns the original placement compiler
against actual ZIP source bytes, proves the child scene and live root
linkage, verifies optional physics/LOD sources against independently
replayed GLBs, and rejects missing, foreign or additional instances.
Source updates fail before the SQLite write if they orphan a mesh, body
or instance. The authoring JSON Schema Draft 2020-12 contract is
`docs/schemas/jeeves-original-mesh-instance-2026.schema.json`.

**Evidence limits:** The source editor now creates game-world hierarchy nodes;
Godot native scene import, actual runtime rendering, contact detection,
behavior and gameplay quality remain unverified until a host-authorized
engine run and separate observation prove them. No model-generated code
gets executable rights merely because it appears in this source.
Coverage: 16 detailed unit/source-store placement cases and two full
native project ZIP roundtrips.

### October 22, 2026 — actual 3D runtime import and exact-candidate evidence

The host-authorized native runner now uses the **exact content-hashed
source-assembled Godot project** whenever original sprites, authored GLB
models or original WAV audio exist. It may not substitute a successful baseline
expedition run for a model-rich project that it never loaded. The older
sprite-only runner entrypoint is retained as a typed wrapper.

The original-3D native verification plane
(`studio_original_mesh_native_probe.py`) installs a trusted,
non-model-authored GDScript into an isolated candidate copy and performs:

1. Godot 4 editor `--headless --import` with real GLB import and strict
   exit/error checks, followed by a separate SceneTree-based engine probe.
2. Loading and instantiation of every approved original `.glb` PackedScene,
   inspection of real `MeshInstance3D` descendants and geometry surfaces,
   and independent import of **each authored LOD GLB**, not only the parent.
3. Real instantiation of each approved Godot physical body/area resource
   with an active `CollisionShape3D`.
4. Loading of the **actual exported game scene**
   `res://game/frontier/expedition.tscn`; inspection of approved
   source-named world mesh instances, numeric positions and authored scale,
   including independently present physics shapes on physical instances.
5. Parsing a single, bounded native `JEEVES_MESH_PROBE` observation.
   Every expected asset/LOD/physics/placement identifier and count must
   match the signed source candidate. A forged extra observation, absent
   model, native import/parse error or timeout fails without a success
   receipt.

Both actual editor import and native probe outputs are directed into
bounded local temporary files, not unbounded subprocess memory buffers.
The installed native binary itself is SHA-256 hashed with streamed reads.
When the Godot process runs successfully, the final original-game native
receipt references the independent mesh-probe receipt and explicitly
records measured counts of imported GLBs, derived LOD meshes, physical
bodies and game-scene instances.

These are **runtime verification capabilities**. Merely committing their
Python source does not mean any installed Godot binary, game window,
screen pixels or collision contacts have been observed in this session.
A source-only ZIP is not proof of Godot execution. The probe intentionally
keeps `native_physics_contacts_observed=false` and
`native_rendered_pixels_observed=false`. Release requires a separate
engine-installed playback result.

**Focused CI:** `backend-quality.yml` now runs the five existing
Jeeves asset compiler test suites as one step in the existing Backend
Quality workflow. It does not add a new workflow or specialized CI gate.
The new adversarial runtime-probe suite contains 24 tests, including
strict exact-candidate routing checks that deliberately mock the Godot
process. Those mocking tests prove routing logic only, not real execution.

### October 22, 2026 — source-owned world-instance descriptors

The separate `studio_world_spatial_index.py` compiler now describes real
`scene_forge.original_mesh_instance` placements **in addition to** standalone
sprite, WAV and GLB asset descriptions. The generated
`game/frontier/assets/world-index.json` is content-addressed and contains:

- The actual authored scene instance ID, source record revision SHA, GLB
  source/bytes SHA, parent asset catalog descriptor SHA and Godot resource path
- Position in integer millimeters, authored rotation and scale, optional
  reviewed collision body and authored LOD availability
- Conservative world-space AABB bounds generated from the compiled glTF
  position accessor bounds. These bounding spheres enclose an arbitrary
  rotation but are **not** true collision shapes or claims of rendered visibility
- Inherited reviewer-approved title, roles and tags, never invented semantics
- Deterministic spatial queries (position, radius, optional physics/visual/LOD
  filters) with result SHA, explicit false runtime-contact claims and bounded
  retrieval sizes

The native creator source owner exposes
`compiled_world_spatial_index()` and
`search_world_instances(center_mm=[x,y,z], radius_mm=n, ...)`. Both
functions read the current creator SQLite revision and refuse an external
source-head change midway through compilation. Source-only projects with
no placements produce an **empty but valid** instance index, rather than
pretending every original GLB is already in a game world.

The post-publication Godot ZIP verifier independently replays the actual
world-instance descriptors from the separately verified `assets/catalog.json`
and authoritative game scene-placement receipt, checking exact JSON bytes,
parent GLB SHA, source revision, physics/LOD relationship and the game
build's world index receipt. It neither trusts unsigned client-supplied
transforms nor treats approximate broad-phase bounds as physics contacts.

Covered by `skeleton/testing/test_jeeves_studio_world_spatial_index_2026.py`
and source-to-ZIP integration tests in
`skeleton/testing/test_jeeves_studio_frontier_source_compile.py`.

### October 22, 2026 — deterministic large-world chunk compilation

The original-game compiler now ships a separate
`game/frontier/assets/world-chunks.json` alongside the existing
`assets/world-index.json` and original sprite/WAV/GLB/LOD/physics
catalogs. `studio_world_chunks.py` hashes and groups every source-owned
3D placement into deterministic 64-meter **home cells**, preserving the
exact source-world SHA-256, placement membership, instance count, and
maximum compiled broadphase radius. Home-cell partitioning is intentionally
small and portable; it does not substitute a physics collision grid.

Jeeves source owner exposes `compiled_world_chunk_catalog()` and
`plan_world_scene_resources(camera_mm, view_radius_mm, previously_loaded,
limit)`. A plan expands the camera's candidate cell set by the largest
real compiled mesh radius and then rechecks original conservative AABBs;
it emits deduplicated, original Godot `.tscn` asset resources to load or
release, ordered by instance proximity. Plans are source-hash linked,
bounded, deterministic and check the previous resource inventory to
prevent accidental foreign paths or model-authored script execution.

The published ZIP's independent verifier rebuilds chunk memberships
from its already verified, immutable 3D world-instance catalog, and
compares both canonical JSON content and SHA-bound source receipt
against the original game source manifest. Unplaced assets do not
appear as fabricated scene instances; projects with no 3D scene placements
produce empty but valid spatial/chunk indexes. Neither the source
catalog nor loading plan alone claims native engine streaming, resource
residency, on-screen rendering or collision contacts.

Validation targets: `test_jeeves_studio_world_chunks_2026.py`
plus two Godot export round trips in
`test_jeeves_studio_frontier_source_compile.py`, now included in
the existing Backend Quality focused test suite.

### Reusable Godot 4 large-world streamer (opt-in, October 2026)

A real `Node3D` resource now ships in every compiled Godot original
game source ZIP: `game/frontier/assets/world_streamer.tscn`, backed by
`game/frontier/assets/world_streamer.gd`. This component parses the
already independently verified `assets/world-index.json` and
`assets/world-chunks.json` source catalogs. With a live 3D camera, it
identifies relevant source-owned home cells, checks conservative source
radius against actual camera distance, instantiates **real** imported
`PackedScene` assets with the exact approved position/rotation/scale,
and frees distant nodes. A maximum of four new scene instances are
created per frame by default (bounded 1–32 setting in Godot); visible
distance is adjustable. Reusable physics-bound `.physics.tscn` and
authored 3D LOD `.lod.tscn` instances are loaded through the same
typed resource route.

**Crucial integration boundary:** the existing default world still
instantiates its original static approved objects. This streaming scene
is a **reusable opt-in alternative**, intentionally *not* autoattached
alongside the static mesh instances: doing so would duplicate models,
colliders and resource loads. An app/game controller may explicitly swap
one for the other after deciding to use runtime streaming. Source
generation is completed, but no actual engine-side streaming, memory
budget, FPS or visual correctness is claimed without an installed
Godot execution result.

The published file SHA identities and an opt-in/runtime-status receipt
are kept in the same source-hashed Godot export; independent ZIP
verification reconstructs the exact `.gd` and `.tscn` bytes,
rejecting substituted scripts even when an archive is self-consistently
rehashed. Tests:
`test_jeeves_studio_world_streamer_2026.py` and the native Godot
ZIP replay cases in `test_jeeves_studio_frontier_source_compile.py`.

### Active (nonduplicating) original-world streaming — Oct 22, 2026

A new optional versioned `scene_forge` source record with
`kind=original_world_streaming_policy`,
`mode=replace_static`, bounded `view_radius_m` and
`instantiate_per_frame` values, and an explicit `depends_on`
reference to an existing original 3D placement now activates **real
Godot runtime streaming in the default expedition scene**.

This is a user-authored opt-in. The exporter replaces the single
`OriginalMeshInstances` PackedScene reference with
`assets/world_streamer.tscn`, instead of attaching a second set of
meshes. The existing non-streaming default is preserved exactly when
no activation record exists. The streaming scene overrides the authored
per-frame instantiation budget and camera radius. The original static
placement source records and child scene are retained in the ZIP as
auditable design history, even when the active root uses streamed
instances instead.

Source records and the activated scene link are SHA-bound in
`assets/world_streaming.source.json`. On published ZIP verification,
Jeeves replays the source policy and **reverses the exact active
root-scene replacement** before separately checking the original
mesh-placement source bundle. Script/source tampering, duplicated
streaming policies, missing placement dependency or inconsistent
root-scene overrides fail closed.

Important: Native static Godot scene verification is **not accepted**
as proof that frame-budgeted streaming occurred. Until a separate
live-camera execution probe confirms spawn/unload transitions, the
runtime certifier explicitly refuses to certify active streaming.
Source scripts are functional artifacts, but mere emitted bytes are
not evidence of observed execution, memory usage or performance.

### Stateful streamed-gameplay objects — October 22, 2026

Godot chunk streaming and the deterministic companion loading planner
now distinguish static source geometry from **simulation-stateful**
`RigidBody3D` and `Area3D` objects. Such objects are retained/pinned
after source generation even when their authored source position falls
outside the camera culling region. The Godot streamer prioritizes them
ahead of regular visual scenery for its per-frame loading budget and
does not free them on camera departure. Static props remain eligible
for unloading as the camera travels.

A request with more persistently stateful objects than the planning
budget is **rejected**, rather than silently evicting bodies and
resetting velocities, triggers or gameplay memory. These rules are
source-based and conservative; runtime physics contacts and GPU
residency are still not certified without observed Godot execution.

The source authoring contract for activating (rather than merely
compiling) a streaming world is
`docs/schemas/jeeves-world-streaming-policy-2026.schema.json`.
The default game remains non-streaming unless the author adds the
explicit versioned `scene_forge` policy record.

### Host-authorized native streaming lifecycle observations (October 2026)

`studio_world_streaming_native_probe.py` provides a second, independent
*installed-Godot* native execution path for games that explicitly activate
`original_world_streaming_policy`. It verifies the canonical published
world/chunk/activation source bytes, SHA-256 ancestry and source-approved
scene patch. A trusted SceneTree GDScript (never an LLM-authored or ZIP-supplied
override) loads the **actual** original game, moves a camera between an authored
scenery instance and a remote position, invokes the real bounded streamer,
and observes:

- A non-stateful reviewed mesh actually instantiates near the camera
- That mesh actually unloads when the camera leaves the authored extent
- Stateful rigid/trigger instances remain the **same nodes** across transit
- No unauthorized scene-instance IDs appear in the live loaded map

The observer requires a single bounded stdout receipt with exact candidate,
world, chunks and policy SHA lineage, unique source-owned instance IDs and
verified near/far node inventories. Host-owned process launch, script path
protection and bounded logs are required; editor/source compilation does not
count as executing the engine. Activated projects with no nonstateful scenery
fail closed for lifecycle certification rather than falsely claiming an unload.
Engine errors, absent observations, spoofed hashes and unverifiable stateful
persistence all deny success.

The existing static-mesh native probe continues to import every original GLB,
LOD and physics resource, but delegates dynamic scene-instance observations
to the camera-transition probe when active streaming is selected. The final
native game receipt records the independent streaming probe digest and the
observed instantiation/unloading/persistent-body counts. Pixels, collision
contacts and GPU residency are still **not** certified by this check.

The focused regression suite
`test_jeeves_studio_world_streaming_native_probe_2026.py`
contains 21 source and adversarial observation tests. These tests use
simulated stdout to check verification logic; only an actual host-authorized
Godot 4 executable run can produce a real streaming-observation receipt.

### Bounded native scene-release work (October 2026)

The source-owned Godot streamer now has an independent, bounded
`release_per_frame` budget of 8 (the source-authored instantiate budget
remains adjustable 1–32). It maintains per-frame and cumulative counters for
real Godot scene-instantiation and queued-release operations. A camera
transition cannot cause unlimited `queue_free()` calls in one frame.

The trusted native observation script checks that the installed Godot
streamer loaded the **authored instantiation budget** and original bounded
release setting and that no observed frame exceeds either value.
This is protection against workload spikes, not a benchmark: emitting the
counters does **not** prove FPS, memory reclamation, collision stability or
rendering quality without actual native execution.
