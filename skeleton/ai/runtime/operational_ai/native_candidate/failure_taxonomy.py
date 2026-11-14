"""Stable training failure categories, never reinterpret a deny as a pass."""
from __future__ import annotations
from .strict import identity

CLASSES = {
    "source-catalog-mismatch": "source-integrity",
    "rights-denied": "source-rights",
    "benchmark-source-contamination": "evaluation-contamination",
    "partition-overlap": "data-leakage",
    "tokenizer-vocabulary-incompatible": "tokenizer",
    "training-step-budget": "resource",
    "training-wall-budget": "resource",
    "trainer-step-mismatch": "runtime",
    "candidate-clone-mismatch": "model-integrity",
    "candidate-restoration-mismatch": "checkpoint-integrity",
    "candidate-parent-unsafe": "filesystem-custody",
    "training-lock-timeout": "concurrency",
    "outbox-conflicting-run": "recovery",
}


def classify(code: str) -> dict:
    identity(code, "failure-code")
    return {
        "code": code,
        "class": CLASSES.get(code, "unclassified"),
        "retry_without_review": False,
        "production_authorized": False,
    }
