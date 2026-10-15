# Jeeves production game training — operator runbook

**Status:** implemented in source; NOT yet compiled or qualified in the running app. No production model weights were changed in this development pass. The scratch RNN and quest-graph ranker are never accepted as production Jeeves weights.

## 1. Compile and boot with durable production state

Install and compile Skeleton using the existing installer/build pipeline. Configure the serving process with a private persistent model-state path:

    export SKELETON_OWN="/PRIVATE_PATH/jeeves-live-own.json"

The path must be private to the serving account, not inside GitHub or a public download directory. The existing production model must have been restored from that file. A new genesis model or a copied scratch checkpoint does NOT establish production custody.

## 2. Obtain an in-process production attestation

Inside the already running, operator-authorized compiled app process, use:

    from pathlib import Path
    from skeleton.cortex.live import status, attest_training_checkpoint
    assert status()["last_load"]["loaded"] is True
    receipt = attest_training_checkpoint(
        Path("/PRIVATE_PATH/operator/jeeves-training-attestation.json")
    )

This requires the running Jeeves singleton. It compares in-memory speaking weights, selected speaking mouth, restored BPE tokenizer and checkpoint content. It never boots a substitute Jeeves process. If the live model has legitimately changed, persist the live state in the existing process before attesting. It writes a new private receipt; no existing output is overwritten. Checkpoint hashes are local integrity/custody records, NOT cryptographic signatures or hardware attestation.

## 3. Read-only training preflight

In the operator environment, point SKELETON_OWN at the exact same checkpoint as the app. The output directory must already exist:

    skeleton-jeeves-production-preflight preflight \
      --attestation /PRIVATE_PATH/operator/jeeves-training-attestation.json \
      --candidate-directory /PRIVATE_PATH/operator/candidates

The preflight checks production path and SHA identity, attestation freshness, active speaking model, tokenizer, architecture, eight-domain game curriculum coverage and free disk space.

To inspect what is missing without authorizing a training run:

    skeleton-jeeves-production-preflight preflight \
      --candidate-directory /PRIVATE_PATH/operator/candidates \
      --allow-unattested-inspection

For native TinyTransformer only, an explicit vocabulary plan may permit adding missing original BPE pieces to a cloned candidate without reindexing or replacing existing learned rows:

    skeleton-jeeves-production-preflight preflight \
      --attestation /PRIVATE_PATH/operator/jeeves-training-attestation.json \
      --candidate-directory /PRIVATE_PATH/operator/candidates \
      --allow-vocabulary-expansion

The opt-in is bounded to 512 new pieces, 4096 total tokens. Torch-stack vocabulary expansion is not implemented; it fails closed when token coverage is insufficient.

## 4. Dry-run before training

    skeleton-jeeves-game-session \
      --run-id game-001 \
      --attestation /PRIVATE_PATH/operator/jeeves-training-attestation.json \
      --output-directory /PRIVATE_PATH/operator/candidates \
      --dry-run

A dry run never changes model weights or publishes a candidate. It returns blockers when production custody is missing.

## 5. Run bounded candidate fine-tuning against actual Jeeves weights

    skeleton-jeeves-game-session \
      --run-id game-001 \
      --attestation /PRIVATE_PATH/operator/jeeves-training-attestation.json \
      --output-directory /PRIVATE_PATH/operator/candidates \
      --epochs 1 \
      --learning-rate 0.005 \
      --max-optimizer-steps 25000 \
      --max-training-seconds 1200

The operator must use a new run ID for every attempt. Append --expand-vocabulary only when explicitly approved by the preflight plan on a native TinyTransformer. Training is not triggered by compiling.

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
      --output-directory /PRIVATE_PATH/operator/candidates \
      --epochs 1 \
      --learning-rate 0.005 \
      --max-optimizer-steps 25000 \
      --max-training-seconds 1200 \
      --resume

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
      skeleton.testing.test_jeeves_training_progress

Separately run the app installer, native runtime, game builder, security, model serving and end-to-end validation after compiling. Source commits alone do not prove those gates passed. No new noisy Actions workflows have been added.

## Work remaining before production readiness

- A real compiled serving process, real SKELETON_OWN checkpoint and in-process attestations are not accessible in this authoring environment.
- An independent evaluation and controlled game playtesting process must establish whether candidate generations materially improve design; lexical/loss metrics are insufficient.
- Torch-stack BPE vocabulary growth is not implemented; low-coverage runs fail closed.
- Interrupted candidate training can resume from immutable per-batch optimizer cursors, but the actual compiled-app restart path still requires end-to-end qualification.
- End-to-end installer/compiled runtime proof and signed model promotion remain open until execution and separate authorization.
