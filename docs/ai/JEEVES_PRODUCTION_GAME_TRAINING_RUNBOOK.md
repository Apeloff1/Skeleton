# Jeeves production game training — operator runbook

**Status:** implemented in source; NOT yet compiled or qualified in the running app. No production model weights were changed in this development pass. The scratch RNN and quest-graph ranker are never accepted as production Jeeves weights.

## 1. Compile and boot with durable production state

Install and compile Skeleton using the existing installer/build pipeline. Configure the serving process with a private persistent model-state path:

    export SKELETON_OWN="/PRIVATE_PATH/jeeves-live-own.json"

The path must be private to the serving account, not inside GitHub or a public download directory. The existing production model must have been restored from that file. A new genesis model or a copied scratch checkpoint does NOT establish production custody.

### Optional first-boot production initialization (no existing checkpoint)

A newly compiled deployment with no actual serving checkpoint cannot be passed
off as previously trained. To create the **app's own** initial trained weights,
use explicit maintenance/bootstrap mode before accepting any user requests:

    export SKELETON_JEEVES_PROFILE=desktop
    export SKELETON_JEEVES_DEVICE=auto
    export SKELETON_JEEVES_BOOTSTRAP=1
    export SKELETON_OWN="/PRIVATE_PATH/jeeves-live-own.json"

The legacy profile remains the default when SKELETON_JEEVES_PROFILE is absent.
Explicit profiles are legacy (8-dimensional native), mobile (32-dimensional
Torch), desktop (128-dimensional Torch), and workstation (256-dimensional
Torch). Nonlegacy profiles require installing the opt-in
jeeves-production-training package extra and compatible PyTorch hardware.
Explicit CUDA or Apple MPS device requests never silently fall back to CPU.

Inside the **same compiled app process** that has initialized its Jeeves
singleton in maintenance mode, call the privileged local Python API:

    from skeleton.cortex.live import get_live, initialize_persisted_production
    get_live()
    receipt = initialize_persisted_production(epochs=1)

This executes actual initial curriculum SGD on that exact app-owned Jeeves,
not a second scratch object. It refuses an existing checkpoint, previously
loaded state, a missing private state path, or more than one epoch. It saves
the initial production checkpoint atomically and requires a FULL app restart
with the same SKELETON_OWN path. Disable SKELETON_JEEVES_BOOTSTRAP after
initialization; restart and confirm the existing weights were restored before
requesting an attestation. This initial curriculum is not evidence of
high-quality game design; game specialization and evaluation follow below.

Choosing a larger profile does **not** upgrade any existing persisted model.
A previously trained checkpoint always controls the restored weight shapes.
Never delete an existing production checkpoint just to change its model size;
use the separate governed architecture migration process.

## 2. Obtain an in-process production attestation

Inside the already running, operator-authorized compiled app process, use:

    from pathlib import Path
    from skeleton.cortex.live import status, attest_training_checkpoint
    assert status()["last_load"]["loaded"] is True
    receipt = attest_training_checkpoint(
        Path("/PRIVATE_PATH/operator/jeeves-training-attestation.json")
    )

This requires the running Jeeves singleton. It compares in-memory speaking weights, selected speaking mouth, restored BPE tokenizer and checkpoint content. It never boots a substitute Jeeves process. If the live model has legitimately changed, persist the live state in the existing process before attesting. It writes a new private receipt; no existing output is overwritten. Checkpoint hashes are local integrity/custody records, NOT cryptographic signatures or hardware attestation.

## 2b. Prepare an approved game-design corpus (mandatory for production session)

The original 40-example Pareto curriculum is a SMALL TEST SET. A genuine
production specialization session requires an operator-supplied JSON manifest
and two separate local JSONL files (train and held-out). No unauthorized
web crawling, rights guessing, or copied third-party game content is
automatically admitted. Each record needs its own documented review of
permission to train or evaluate.

Manifest (replace the hashes with SHA-256 of the EXACT files):

    {
      "schema_version": "skeleton.jeeves.game_corpus_manifest.v1",
      "rights_reviewed": true,
      "review_id": "legal-approved-original-game-corpus-001",
      "train_file": "game-train.jsonl",
      "train_sha256": "<64 hex SHA-256>",
      "heldout_file": "game-heldout.jsonl",
      "heldout_sha256": "<64 hex SHA-256>"
    }

Each JSONL record has the same fields:

    {
      "id": "original_mechanics_001",
      "source_project_id": "original_game_project_001",
      "split": "train",
      "family": "mechanics",
      "prompt": "Design an original reversible two-button climbing challenge.",
      "answer": "A valid detailed design must supply player controls, feedback, failure recovery, replay outcomes and constraints.",
      "rights": {
        "schema_version": "skeleton.jeeves.game_corpus_rights.v1",
        "source_kind": "original_authoring",
        "rights_holder": "Actual rights owner",
        "rights_basis": "Actual documented grant or original authorship",
        "review_id": "rights-review-001",
        "training_permitted": true
      }
    }

The snippet illustrates the schema, NOT independently validated permission or
a high-quality training example. Review actual rights before setting
training_permitted=true. The loader rejects source_kind=unverified_scrape,
unknown licensing, malformed rights declarations, edited files, duplicates
and near-copied evaluation prompts/answers. It also excludes overlap with
the separate 24-question human game-design benchmark.

The source_project_id is mandatory. Every source project belongs entirely
to TRAIN or HELDOUT, never both; this guards against copying scenes from one
world between splits. At least two independent source projects are required
in each split, and copied or near-copied benchmark questions are rejected.

The app also has an optional builder for converting already human-reviewed
game-work artifacts into a validated dataset. A reviewed intake is JSONL
containing schema_version "skeleton.jeeves.reviewed_game_design_intake.v1",
a unique id and source_project_id, family, prompt and answer, rights metadata,
quality_approved=true, a named quality_reviewer_id, and an evidence-bearing
quality_review_note. Those approvals are supplied by real operators; the app
does not automatically decide ownership or invent reviewers.

    skeleton-jeeves-corpus-build \
      --intake /PRIVATE_PATH/reviews/reviewed-game-examples.jsonl \
      --output-dir /PRIVATE_PATH/corpora \
      --prefix approved_game_v001 \
      --partition-seed approved_holdout_001 \
      --rights-review-id original_sources_rights_001

The builder groups all examples from a source game project together,
deterministically selects held-out PROJECTS while preserving each domain's
minimum training quota, runs the production loader on the staged output,
then exclusively publishes two JSONL files and a SHA-pinned manifest.
A builder receipt remains a review declaration, NOT legal verification
or proof of game-design quality.

All eight families need at least four TRAIN examples and two HELDOUT examples:
mechanics, narrative, npc, world, economy, tooling, accessibility and review.
This is a minimum STRUCTURAL validity threshold, NOT a recommended dataset
size or guarantee of creativity. The entire production pipeline also admits
only bounded optimizer-step budgets, which may require multiple reviewed runs
for truly large corpora.

Validate the corpus independently BEFORE reading production weights:

    skeleton-jeeves-game-corpus --manifest /PRIVATE_PATH/corpora/game-manifest.json

Then use --dataset-manifest with every preflight, backup, dry-run, training
and resume command below. The dataset manifest hash is bound to saved
optimizer progress. An edited corpus invalidates its original admission.

## 3. Read-only training preflight

In the operator environment, point SKELETON_OWN at the exact same checkpoint as the app. The output directory must already exist:

    skeleton-jeeves-production-preflight preflight \
      --attestation /PRIVATE_PATH/operator/jeeves-training-attestation.json \
      --dataset-manifest /PRIVATE_PATH/corpora/game-manifest.json \
      --candidate-directory /PRIVATE_PATH/operator/candidates

The preflight checks production path and SHA identity, attestation freshness, active speaking model, tokenizer, architecture, eight-domain game curriculum coverage and free disk space.

To inspect what is missing without authorizing a training run:

    skeleton-jeeves-production-preflight preflight \
      --candidate-directory /PRIVATE_PATH/operator/candidates \
      --allow-unattested-inspection

For TinyTransformer or Torch-stack, an explicit vocabulary plan may permit adding missing original BPE pieces (native) or word tokens (Torch) to a cloned candidate without reindexing or replacing existing learned rows:

    skeleton-jeeves-production-preflight preflight \
      --attestation /PRIVATE_PATH/operator/jeeves-training-attestation.json \
      --dataset-manifest /PRIVATE_PATH/corpora/game-manifest.json \
      --candidate-directory /PRIVATE_PATH/operator/candidates \
      --allow-vocabulary-expansion

Native growth is bounded to 512 BPE pieces, 4096 total tokens. Torch-stack growth is bounded to 1024 word tokens, 8192 total tokens; it preserves existing embedding/projection rows, rebinds the SGD optimizer and requires exact token order on checkpoint restore. Both refuse exceeding their budgets.

## 4. Dry-run before training

    skeleton-jeeves-game-session \
      --run-id game-001 \
      --attestation /PRIVATE_PATH/operator/jeeves-training-attestation.json \
      --dataset-manifest /PRIVATE_PATH/corpora/game-manifest.json \
      --output-directory /PRIVATE_PATH/operator/candidates \
      --dry-run

A dry run never changes model weights or publishes a candidate. It returns blockers when production custody is missing.

## 5. Run bounded candidate fine-tuning against actual Jeeves weights

    skeleton-jeeves-game-session \
      --run-id game-001 \
      --attestation /PRIVATE_PATH/operator/jeeves-training-attestation.json \
      --dataset-manifest /PRIVATE_PATH/corpora/game-manifest.json \
      --output-directory /PRIVATE_PATH/operator/candidates \
      --epochs 1 \
      --learning-rate 0.005 \
      --max-optimizer-steps 25000 \
      --max-training-seconds 1200

The operator must use a new run ID for every attempt. Append --expand-vocabulary only when explicitly approved by the preflight plan for the active native or Torch model. Training is not triggered by compiling.

Training protects the original parent checkpoint, writes an immutable verified backup, fits only a cloned active speaking model, enforces optimizer-update quotas and batch-boundary elapsed-time quotas, evaluates held-out loss on eight training domains and saves generated parent/candidate answers on 24 further never-trained game-design prompts. A time limit is checked between batches, not as hard preemption inside an individual optimizer call.

## 6. Review files and gate promotion

Every normal session also commits content-addressed, production-parent-bound
optimizer snapshots and ordered progress receipts **after each eight-document
batch**. An interrupted attempt can resume using the SAME run ID, the same
policy and dataset, the same active model weights, and a fresh valid live
attestation. The run checks stage-zero weights against freshly restored
production weights, then verifies each cursor and immutable snapshot before
continuing. An unverified or missing stage is rejected, not skipped.

    skeleton-jeeves-game-session \
      --run-id game-001 \
      --attestation /PRIVATE_PATH/operator/jeeves-training-attestation.json \
      --dataset-manifest /PRIVATE_PATH/corpora/game-manifest.json \
      --output-directory /PRIVATE_PATH/operator/candidates \
      --epochs 1 \
      --learning-rate 0.005 \
      --max-optimizer-steps 25000 \
      --max-training-seconds 1200 \
      --resume

When actual optimizer training has finished and the candidate plus training
report are already written, but the independent game-design review or final
manifest failed, use the POST-SGD recovery command instead of --resume:

    skeleton-jeeves-session-recover \
      --run-id game-001 \
      --attestation /PRIVATE_PATH/operator/jeeves-training-attestation.json \
      --dataset-manifest /PRIVATE_PATH/corpora/approved_game_v001-manifest.json \
      --output-directory /PRIVATE_PATH/operator/candidates

This checks the same serving parent and approved corpus, verifies candidate
lineage and SGD steps, regenerates the independent 24-prompt model comparison,
refuses mismatched existing review files, and exclusively writes the final
session manifest. It neither retrains nor promotes a model.

A completed/rejected run with a manifest cannot be resumed as though unfinished;
start a distinct run ID instead. Resume does not modify the live parent file
or authorize deployment. The progress folder must be privately writable by
the operator; its SHA-256 digests provide tamper detection, not an independent
signature against someone able to rewrite all local files.

A completed candidate run writes the following separate output files:

- game-001-parent-backup.json — byte-identical, verified production baseline copy
- game-001-candidate.json — trained, unpromoted full Jeeves state
- game-001-training.json — held-out losses, generations and training receipts
- game-001-game-review.json — actual parent vs candidate design generations and independent-review questions
- game-001-manifest.json — exact output hashes and non-promotion proof

Training a candidate is not automatic production activation. The app's existing shadow-weight ledger, independent admission, reviewer signoff, rollback and serving-pointer activation remain the only paths to promotion. Keyword matches or prediction-loss improvements are NOT proof of better game design.

## 7. Blinded independent game-design review

Production model learning is not considered effective just because perplexity
falls. Prepare a genuinely blinded game-design comparison from the operator's
game-review file:

    skeleton-jeeves-game-review prepare \
      --benchmark /PRIVATE_PATH/operator/candidates/game-001-game-review.json \
      --packet /PRIVATE_PATH/operator/reviews/blind-packet.json \
      --private-key /PRIVATE_PATH/operator/private/candidate-key.json

The private identity key must stay with the adjudicator. Give only
blind-packet.json to two independent reviewers. Create empty review sheets:

    skeleton-jeeves-game-review worksheet \
      --packet /PRIVATE_PATH/operator/reviews/blind-packet.json \
      --reviewer-id reviewer-alpha \
      --output /PRIVATE_PATH/operator/reviews/reviewer-alpha.json

Repeat with a distinct reviewer ID and destination. Every blank sheet contains
all 24 prompts, six criteria per response, critical-defect flags, and empty
evidence notes. **No scores are filled in automatically.**

After independent reviewers have completed all scores and factual evidence
notes, adjudicate the two worksheets:

    skeleton-jeeves-game-review adjudicate \
      --packet /PRIVATE_PATH/operator/reviews/blind-packet.json \
      --private-key /PRIVATE_PATH/operator/private/candidate-key.json \
      --reviewer-a /PRIVATE_PATH/operator/reviews/reviewer-alpha.json \
      --reviewer-b /PRIVATE_PATH/operator/reviews/reviewer-beta.json \
      --output /PRIVATE_PATH/operator/private/adjudication.json

A candidate must improve average ratings, avoid critical defects, avoid
meaningful domain regressions, and pass at least 20 of 24 non-regression
comparisons agreed upon by both reviewers. This gate only makes a candidate
eligible for a *separate* governed promotion proposal. It never activates
production weights. Reviewer judgments remain subjective and should ultimately
be complemented by playable tests with real players.

## 8. Tests and compile gates

Run:

    python -m unittest \
      skeleton.testing.test_jeeves_production_game_train \
      skeleton.testing.test_jeeves_production_training_operator \
      skeleton.testing.test_jeeves_cortex_persisted_bpe \
      skeleton.testing.test_jeeves_game_design_review_gate \
      skeleton.testing.test_jeeves_training_progress \
      skeleton.testing.test_jeeves_torch_game_vocabulary \
      skeleton.testing.test_jeeves_production_profile \
      skeleton.testing.test_jeeves_game_corpus \
      skeleton.testing.test_jeeves_game_corpus_builder \
      skeleton.testing.test_jeeves_production_game_recovery

Separately run the app installer, native runtime, game builder, security, model serving and end-to-end validation after compiling. Source commits alone do not prove those gates passed. No new noisy Actions workflows have been added.

## Work remaining before production readiness

- A real compiled serving process, real SKELETON_OWN checkpoint and in-process attestations are not accessible in this authoring environment; the guarded first-boot flow is implemented but remains unverified on a compiled installation.
- An independently reviewed, permission-cleared, high-quality game-design corpus must be provided; no such large approved dataset is included in source. Independent evaluation and controlled playtesting must establish whether candidate generations materially improve design.
- Torch-stack vocabulary growth now supports preserved token IDs, but compiled GPU/CPU training performance and post-reload behavior remain to be verified end-to-end.
- Interrupted candidate training can resume from immutable per-batch optimizer cursors, but the actual compiled-app restart path still requires end-to-end qualification.
- End-to-end installer/compiled runtime proof and signed model promotion remain open until execution and separate authorization.
