"""All uncertain native training and assessment failures keep promotion denied."""
from __future__ import annotations
from .canonical import require_id

CLASSES={
    "source-incomplete":"source-integrity",
    "source-truth":"source-integrity",
    "challenge-exact-contamination":"evaluation-integrity",
    "train-only-partition":"training-scope",
    "heldout-train-forbidden":"data-leakage",
    "prompt-context-exceeds-claimed-budget":"context-ceiling",
    "target-optimizer-budget":"training-resource",
    "optimizer-wall-budget":"training-resource",
    "optimizer-invalid-loss":"gradient-integrity",
    "train-no-qualified-validation-improvement":"quality-hold",
    "training-proof-checkpoint-hash":"checkpoint-integrity",
    "store-parent-custody":"artifact-custody",
    "store-existing-artifact-held":"partial-recovery",
    "probe-model-drift":"runtime-integrity",
    "challenge-incomplete-source":"evaluation-integrity",
    "pair-source-drift":"comparison-integrity",
    "epoch-chain-pinned-head":"audit-integrity",
    "run-transition":"state-authority",
    "authority-collision":"independent-review",
}


def classify(code:str)->dict:
    require_id(code,"failure")
    return {
        "error_code":code,"category":CLASSES.get(code,"unclassified"),
        "retry_without_manual_review":False,
        "training_success_claimed":False,
        "production_authorized":False,
    }
