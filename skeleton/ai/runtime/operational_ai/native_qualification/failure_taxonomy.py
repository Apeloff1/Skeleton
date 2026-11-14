"""Stable evidence category mapping, separating runtime failures from quality failures."""
from __future__ import annotations
from .canonical import identity

KINDS = frozenset({
    "quality-mismatch", "native-call-failed", "native-empty-generation",
    "native-receipt-identity", "native-replayed-generation", "native-revision",
    "response-oversize", "case-timeout", "case-latency-exceeded",
    "run-time-budget", "unknown",
})
CATEGORIES = {
    "quality-mismatch": "model-quality",
    "native-call-failed": "native-runtime",
    "native-empty-generation": "native-runtime",
    "native-receipt-identity": "integrity",
    "native-replayed-generation": "integrity",
    "native-revision": "durable-recovery",
    "response-oversize": "resource",
    "case-timeout": "resource",
    "case-latency-exceeded": "resource",
    "run-time-budget": "resource",
    "unknown": "unclassified",
}


def classify(error_code: str | None, *, checks_passed: bool) -> str:
    if error_code is None:
        return "passed" if checks_passed else CATEGORIES["quality-mismatch"]
    identity(error_code, "error")
    return CATEGORIES.get(error_code, "unclassified")
