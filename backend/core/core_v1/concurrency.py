"""Optimistic concurrency via strong ETags derived from (id, version)."""
from __future__ import annotations

import hashlib

from .errors import precondition_failed, precondition_required


def etag(resource_id: str, version: int) -> str:
    digest = hashlib.sha256(f"{resource_id}:{version}".encode()).hexdigest()[:20]
    return f'"{digest}"'


def check_if_match(if_match: str | None, resource_id: str, version: int,
                   required: bool = True) -> None:
    current = etag(resource_id, version)
    if if_match is None or not if_match.strip():
        if required:
            raise precondition_required()
        return
    candidates = [c.strip() for c in if_match.split(",")]
    if "*" in candidates:
        return
    # weak comparison is not allowed for writes (RFC 9110 13.1.1)
    if current not in candidates:
        raise precondition_failed(current)
