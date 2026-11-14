"""Fail-closed and privacy-safe genesis error classification."""
from __future__ import annotations
from .canonical import required_id

CODES={
    "operator-approval-required":"operator-identity",
    "production-promotion-refused":"training-scope",
    "source-inventory-incomplete":"source-integrity",
    "original-answer-mismatch":"source-truth",
    "benchmark-contaminated-source":"data-contamination",
    "vocabulary-capacity":"tokenizer-capacity",
    "vocabulary-line-budget":"resource-ceiling",
    "estimated-model-budget":"resource-ceiling",
    "genesis-model-storage-over-budget":"resource-ceiling",
    "genesis-checkpoint-roundtrip":"checkpoint-integrity",
    "genesis-tokenizer-roundtrip":"tokenizer-integrity",
    "store-owner-mismatch":"filesystem-ownership",
    "store-untrusted-directory":"filesystem-custody",
    "genesis-path-already-exists":"ambiguous-recovery",
    "checkpoint-hash-mismatch":"artifact-tamper",
    "evaluation-model-identity":"model-identity",
}


def classify(code:str)->dict:
    required_id(code,"failure")
    return {
        "code":code,"category":CODES.get(code,"unclassified"),
        "retry_without_manual_review":False,
        "production_authorized":False,
    }
