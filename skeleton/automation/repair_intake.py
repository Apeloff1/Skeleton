"""Deterministic helpers for safe repair-intake identity and metadata."""

from __future__ import annotations

import hashlib
import re

_FINGERPRINT_RE = re.compile(r"[0-9a-f]{64}\Z")


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def intake_fingerprint(
    workflow: str,
    conclusion: str,
    head_sha: str,
) -> str:
    """Return a stable identity for one workflow/head failure observation.

    Run IDs are intentionally excluded so reruns of the same workflow at the
    same commit correlate to one durable intake record instead of creating a
    new issue for every attempt.
    """

    values = (
        _required_text(workflow, "workflow").lower(),
        _required_text(conclusion, "conclusion").lower(),
        _required_text(head_sha, "head_sha").lower(),
    )
    return hashlib.sha256("\x1f".join(values).encode("utf-8")).hexdigest()


def issue_marker(fingerprint: str) -> str:
    """Return the exact machine-readable marker used for issue deduplication."""

    if not isinstance(fingerprint, str):
        raise TypeError("fingerprint must be a string")
    if not _FINGERPRINT_RE.fullmatch(fingerprint):
        raise ValueError("fingerprint must be a lowercase sha256 digest")
    return f"<!-- repair-intake:fingerprint={fingerprint} -->"
