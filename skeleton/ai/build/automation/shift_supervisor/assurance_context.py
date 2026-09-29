from __future__ import annotations

"""Deterministic assurance metadata boundary for shift supervisor flows.

This module intentionally does not execute work or call models. It provides a
small immutable-style context object that can be attached to supervisor events
for provenance and replay-safe tracing.
"""

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class AssuranceContext:
    actor: str
    correlation_id: str
    operation: str
    payload_digest: str
    version: int = 1


def build_assurance_context(
    *,
    actor: str,
    correlation_id: str,
    operation: str,
    payload: Mapping[str, Any],
) -> AssuranceContext:
    canonical = json.dumps(dict(payload), sort_keys=True, default=str, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return AssuranceContext(
        actor=str(actor),
        correlation_id=str(correlation_id),
        operation=str(operation),
        payload_digest=digest,
    )


def validate_assurance_context(context: AssuranceContext) -> bool:
    return bool(
        context.actor.strip()
        and context.correlation_id.strip()
        and context.operation.strip()
        and len(context.payload_digest) == 64
    )
