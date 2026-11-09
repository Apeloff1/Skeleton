"""New local Functional AI operations must have truthful UTC creation evidence."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from skeleton.ai.runtime.functional_ai import FunctionalAIRequest


def request(**overrides):
    fields = {
        "request_id": "functional-request-clock-1",
        "objective": "Build a deterministic test scene",
        "prompt": "Create a scene",
        "instructions": "No external providers",
        "context_digest": "a" * 64,
    }
    fields.update(overrides)
    return FunctionalAIRequest(**fields)


def test_new_request_timestamp_reflects_creation_not_module_import() -> None:
    before = datetime.now(timezone.utc)
    obj = request()
    after = datetime.now(timezone.utc)
    assert before <= obj.created_at <= after
    assert obj.created_at.utcoffset() == timedelta(0)


def test_generated_operation_preserves_creation_receipt_time() -> None:
    obj = request(request_id="clock-2")
    assert obj.to_execution_request().created_at == obj.created_at


def test_explicit_aware_instant_is_preserved_in_utc() -> None:
    local = timezone(timedelta(hours=2))
    instant = datetime(2026, 10, 26, 10, 30, tzinfo=local)
    obj = request(created_at=instant)
    assert obj.created_at == datetime(2026, 10, 26, 8, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize("invalid", ["2026-10-26", 0, None, datetime(2026, 10, 26)])
def test_invalid_or_naive_created_at_fails_with_typed_validation(invalid) -> None:
    with pytest.raises(ValueError, match="created_at must be timezone-aware"):
        request(created_at=invalid)
