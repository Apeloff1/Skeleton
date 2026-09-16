"""Deterministic helpers for safe repair-intake identity and metadata."""

from __future__ import annotations

import hashlib


def intake_fingerprint(
    workflow: str,
    conclusion: str,
    head_sha: str,
    run_id: str,
) -> str:
    """Return a stable identity for one workflow-run observation."""
    values = (
        workflow.strip().lower(),
        conclusion.strip().lower(),
        head_sha.strip().lower(),
        str(run_id).strip(),
    )
    return hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()


def issue_marker(fingerprint: str) -> str:
    """Return the machine-readable marker used for exact issue deduplication."""
    return f"<!-- repair-intake:fingerprint={fingerprint} -->"
