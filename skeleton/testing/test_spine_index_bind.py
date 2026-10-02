from __future__ import annotations

from skeleton.persistence.spine_bind_audit import SpineBindAudit, SpineBindAuditError
from skeleton.persistence.spine_index_bind import SpineIndexBind


class _Indexed:
    def __init__(self) -> None:
        self.calls = 0

    def create_index(self, keys, unique: bool = False) -> None:
        self.calls += 1


class _Plain:
    pass


class _Runtime:
    def dispatcher_running(self) -> bool:
        return False


def test_missing_method_is_skipped_and_motor_stays_off() -> None:
    receipts = _Indexed()
    card = SpineIndexBind().bind({"receipts": receipts, "watermarks": _Plain(), "fence": _Plain()})
    assert card["created"] == 1
    assert card["skipped"] == 2
    assert card["live_motor"] is False
    assert card["completion_checkbox"] is False
    assert receipts.calls == 1


def test_missing_collection_is_not_a_live_bootstrap() -> None:
    card = SpineIndexBind().bind({})
    assert card["missing"] == 3
    assert card["created"] == 0
    assert card["live_motor"] is False
    assert card["hit"] is False


def test_bind_audit_refuses_a_running_dispatcher() -> None:
    card = SpineBindAudit().audit(_Runtime(), {"runtime_replaced": False})
    assert card["dispatcher_running"] is False
    assert card["live_motor"] is False

    class Running(_Runtime):
        def dispatcher_running(self) -> bool:
            return True

    try:
        SpineBindAudit().audit(Running(), {"runtime_replaced": False})
    except SpineBindAuditError as exc:
        assert "running" in str(exc)
    else:
        raise AssertionError("running dispatcher must fail closed")
