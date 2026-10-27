"""Canonical provider delta timestamps must represent real aware instants."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from skeleton.provider_runtime import (
    ProviderProtocolViolationError,
    ProviderResponse,
    provider_response_deltas,
)


def response() -> ProviderResponse:
    return ProviderResponse(text="safe output", provider="test-provider", model="test-model")


@pytest.mark.parametrize("invalid", [
    datetime(2026, 10, 26, 12, 30), "2026-10-26T12:30:00Z", 0, object(),
])
def test_naive_or_nondatetime_emission_override_fails_closed(invalid) -> None:
    with pytest.raises(ProviderProtocolViolationError, match="emitted_at must be timezone-aware"):
        provider_response_deltas(response(), emitted_at=invalid)


def test_explicit_aware_offset_is_normalized_for_every_delta() -> None:
    local = timezone(timedelta(hours=2))
    instant = datetime(2026, 10, 26, 12, 30, tzinfo=local)
    deltas = provider_response_deltas(response(), emitted_at=instant)
    expected = datetime(2026, 10, 26, 10, 30, tzinfo=UTC)
    assert len(deltas) == 3
    assert [item.sequence for item in deltas] == [0, 1, 2]
    assert all(item.emitted_at == expected and item.emitted_at.tzinfo == UTC for item in deltas)


def test_unspecified_event_time_is_generated_aware_utc() -> None:
    before = datetime.now(UTC)
    deltas = provider_response_deltas(response())
    after = datetime.now(UTC)
    assert deltas
    assert all(before <= item.emitted_at <= after for item in deltas)
    assert all(item.emitted_at.tzinfo == UTC for item in deltas)


def test_response_type_is_checked_before_timestamp_override() -> None:
    with pytest.raises(TypeError, match="response must be ProviderResponse"):
        provider_response_deltas(None, emitted_at=datetime(2026, 10, 26))
