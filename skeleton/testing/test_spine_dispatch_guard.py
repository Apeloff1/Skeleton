from __future__ import annotations

import pytest

from skeleton.persistence.spine_dispatch_guard import (
    SpineDispatchGuard,
    SpineDispatchGuardError,
)


class _Runtime:
    def __init__(self) -> None:
        self.calls = 0

    def start_dispatcher(self) -> bool:
        self.calls += 1
        return True


def test_bound_method_identity_is_stable_without_invocation() -> None:
    runtime = _Runtime()
    guard = SpineDispatchGuard()

    before = guard.snapshot(runtime)
    after = guard.compare(before, runtime)

    assert before["binding_kind"] == "bound-method"
    assert before["callable_id"] == after["callable_id"]
    assert before["owner_id"] == after["owner_id"]
    assert after["same"] is True
    assert after["called"] is False
    assert runtime.calls == 0
    assert after["completion_checkbox"] is False


def test_replaced_dispatcher_callable_fails_closed() -> None:
    runtime = _Runtime()
    guard = SpineDispatchGuard()
    before = guard.snapshot(runtime)

    runtime.start_dispatcher = lambda: False  # type: ignore[method-assign]

    with pytest.raises(SpineDispatchGuardError, match="identity changed"):
        guard.compare(before, runtime)
    assert runtime.calls == 0


def test_rebinding_to_another_runtime_fails_closed() -> None:
    first = _Runtime()
    second = _Runtime()
    guard = SpineDispatchGuard()
    before = guard.snapshot(first)

    with pytest.raises(SpineDispatchGuardError, match="identity changed"):
        guard.compare(before, second)
    assert first.calls == 0
    assert second.calls == 0


@pytest.mark.parametrize(
    "before",
    [
        None,
        {},
        {"kind": "wrong"},
        {"kind": "spine_dispatch_guard", "callable_id": 1},
    ],
)
def test_incomplete_identity_card_fails_closed(before) -> None:
    with pytest.raises(SpineDispatchGuardError):
        SpineDispatchGuard().compare(before, _Runtime())
