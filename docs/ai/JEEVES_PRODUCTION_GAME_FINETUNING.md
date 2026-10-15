# Production Jeeves game specialization: exact-checkpoint gate

## Scope

This operator is different from the previous byte-level recurrent exercise and
the experimental quest-graph ranker. It fine-tunes a clone of the **persisted
JeevesCortex transformer** only after verifying the real live state file
configured by `SKELETON_OWN`. There is **no newly initialized model fallback**,
no simulated result, and no provider/model API training.

The live Jeeves cortex uses `skeleton/cortex/live.py` and
`skeleton/cortex/neocortex.py`. The persistent state contains the actual
`transformer` tensor snapshot and the rest of its own system (own, lms,
acquired, shadow, etc.). Other native serving surfaces may use a separate
`NativeLLMRuntime` and operator-supplied checkpoint directory, and external
providers do **not** expose provider weights to Skeleton. Those formats are
not passed into this operator; do not misidentify them as the production
JeevesCortex snapshot.

## Required operator access

On the **machine/process that actually serves Jeeves**, find the active
`SKELETON_OWN` setting and its checkpoint file.

For example, in a shell with the serving environment already configured:

    test -n "${SKELETON_OWN:-}" || { echo 'Production checkpoint not configured'; exit 2; }
    test -f "$SKELETON_OWN" || { echo 'Production checkpoint absent'; exit 2; }
    sha256sum "$SKELETON_OWN"

This hash is the source identity to pin. Ideally cross-check it against the
live serving process/ledger or an independently witnessed runtime snapshot.
A random model file copied from another machine is **not** proof of
production identity.

When the same configured live checkpoint is available to the training
process, run:

    python -m skeleton.ai.training.jeeves_production_game_train \
      --expected-sha256 YOUR_VERIFIED_CHECKPOINT_SHA256 \
      --candidate ./jeeves-game-candidate.json \
      --report ./jeeves-game-evaluation.json \
      --epochs 1

The process refuses if `SKELETON_OWN` is unset, the checkpoint is missing,
an explicit path differs from `SKELETON_OWN`, the hash differs, or the
snapshot lacks an existing weight-bearing trained transformer. This is by
design: GitHub repository write permission is **not** access to live
production model memory or disk.

## Evaluation and promotion

The trainer clones existing native transformer tensors. It does not mutate
`SKELETON_OWN` or replace the active model pointer.

Before any weight changes, it requires at least **80% actual vocabulary
coverage** over training and evaluation inputs, because specializing a small
fixed-vocabulary transformer with mostly unknown tokens is not meaningful.
It applies at most 3 epochs and a 0.03 learning rate.

Evaluation uses 16 independently authored held-out cases over 8 game-design
domains. It records aggregate and family losses **and actual generated
before/after answers**, so a reviewer can inspect whether game-design
behavior improved. A new candidate is written only when held-out aggregate
loss improves, no domain loss regresses beyond the policy, and the original
checkpoint remains unchanged at the same SHA-256.

Even an accepted candidate is marked
`candidate_trained_needs_game_design_review`, with
`game_design_improvement_established: false`. **Loss is not proof of
successful game design.** Independent tasks on mechanics, authored quest
solvability, branching dialogue, NPC canon, player choice, and game quality
must improve before promotion. The production serving-plane promotion
authority remains separate.

## Why no live training was reported on 2026-10-15

The available sandbox contained the previously created experimental NumPy
recurrent checkpoint and quest-ranking adapter, but **not**
`SKELETON_OWN`, a persisted JeevesCortex snapshot, or a native
production checkpoint. The connected GitHub repository holds source code,
not the serving process's runtime checkpoint. The connected Hugging Face
account had no visible compute jobs; its model-list tool was unavailable.
Consequently the required production checkpoint is **not accessible** and
no production model weight update is claimed.

This module and its fail-closed tests can be executed on the serving machine
once the real checkpoint is available. No extra GitHub Actions workflows or
implicit paid jobs are introduced.
