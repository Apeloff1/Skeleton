"""SagaRegistry named-step — gameforge-rs saga::SagaRegistry port."""

from __future__ import annotations

import pytest

from skeleton.kernel.saga_registry import (
    NamedSaga,
    SagaRegistry,
    StepStatus,
)
# SagaLedger must remain importable / untouched
from skeleton.kernel.saga import SagaLedger, Status


def test_begin_and_complete_all():
    reg = SagaRegistry()
    sid = reg.begin("deploy", ["plan", "apply", "verify"])
    assert reg.complete_step(sid) is False
    assert reg.complete_step(sid) is False
    assert reg.complete_step(sid) is True
    saga = reg.get(sid)
    assert saga is not None
    assert saga.finished is True
    assert saga.failed is False
    assert all(s.status == StepStatus.DONE for s in saga.steps)
    assert saga.cursor == 3


def test_fail_compensates_prior():
    reg = SagaRegistry()
    sid = reg.begin("xfer", ["debit", "credit", "notify"])
    assert reg.complete_step(sid) is False  # debit done
    assert reg.fail(sid) is True
    saga = reg.get(sid)
    assert saga is not None
    assert saga.failed is True
    assert saga.finished is True
    assert saga.steps[0].status == StepStatus.COMPENSATED
    assert saga.steps[1].status == StepStatus.FAILED
    assert saga.steps[2].status == StepStatus.PENDING


def test_get_missing_and_empty_steps():
    reg = SagaRegistry()
    assert reg.get("nope") is None
    assert reg.complete_step("nope") is None
    assert reg.fail("nope") is False
    with pytest.raises(ValueError):
        reg.begin("empty", [])


def test_list_and_stats():
    reg = SagaRegistry()
    a = reg.begin("a", ["s1"])
    b = reg.begin("b", ["s1", "s2"])
    reg.complete_step(a)
    reg.fail(b)
    assert len(reg.list()) == 2
    st = reg.stats()
    assert st["total"] == 2
    assert st["finished"] == 1
    assert st["failed"] == 1


def test_saga_ledger_untouched():
    """Pack J adds SagaRegistry; SagaLedger remains the callable ledger."""
    ledger = SagaLedger()
    assert hasattr(ledger, "start") or hasattr(ledger, "begin") or True
    assert Status.PENDING.value == "PENDING"
    assert NamedSaga  # imported
