"""Deterministic task identity helpers for canonical automation envelopes."""

from __future__ import annotations

import hashlib
import json

from skeleton.contracts.canonical import CanonicalEnvelope


class TaskIdentityError(ValueError):
    """Raised when a task identity cannot be derived."""


def derive_task_identity(envelope: CanonicalEnvelope) -> str:
    """Return a stable queue identity from a validated canonical envelope."""
    payload = {
        "digest": envelope.digest,
        "kind": envelope.kind,
        "repository": envelope.identity.repository,
        "commit_sha": envelope.identity.commit_sha,
    }
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
