from __future__ import annotations

import hashlib

from core.shift_supervisor.assurance_context import AssuranceContext


def test_assurance_context_digest_is_deterministic() -> None:
    first = AssuranceContext.create(
        actor="worker",
        correlation_id="corr-1",
        operation="build",
        payload={"b": 2, "a": 1},
    )
    second = AssuranceContext.create(
        actor="worker",
        correlation_id="corr-1",
        operation="build",
        payload={"a": 1, "b": 2},
    )

    assert first.digest == second.digest
    assert len(first.digest) == hashlib.sha256().digest_size * 2


def test_assurance_context_requires_identity() -> None:
    context = AssuranceContext.create(
        actor="",
        correlation_id="corr-2",
        operation="build",
        payload={},
    )

    assert not context.is_valid()
