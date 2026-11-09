from __future__ import annotations

from datetime import datetime, timezone

import pytest

from skeleton.persistence.spine_driver_selection import (
    SpineDriverSelectionError,
    SpineDriverSelectionLedger,
)
from skeleton.persistence.spine_driver_selection_verify import SpineDriverSelectionVerify


NOW = datetime(2026, 10, 1, 16, 10, tzinfo=timezone.utc)


def _consumption() -> dict[str, object]:
    return {
        "kind": "spine_selection_consumption",
        "digest": "c" * 64,
        "permit_id": "p" * 64,
        "target_driver": "pymongo-async",
        "selection_authorized": True,
        "permit_consumed": True,
        "runtime_driver_selected": False,
        "runtime_activated": False,
    }


def _consumption_verify() -> dict[str, object]:
    return {
        "kind": "spine_selection_consumption_verify",
        "consumption_digest": "c" * 64,
        "permit_id": "p" * 64,
        "verified": True,
        "selection_authorized": True,
        "permit_consumed": True,
        "runtime_driver_selected": False,
        "runtime_activated": False,
    }


def test_consumed_permit_persists_selected_driver_without_activation() -> None:
    ledger = SpineDriverSelectionLedger()
    try:
        card = ledger.select(
            consumption=_consumption(),
            consumption_verify=_consumption_verify(),
            now=NOW,
        )
        verified = SpineDriverSelectionVerify().verify(card)

        assert ledger.count() == 1
        assert card["target_driver"] == "pymongo-async"
        assert card["runtime_driver_selected"] is True
        assert card["runtime_object_replaced"] is False
        assert card["dispatcher_started"] is False
        assert card["runtime_activated"] is False
        assert verified["verified"] is True
        assert verified["runtime_driver_selected"] is True
        assert verified["runtime_activated"] is False
    finally:
        ledger.close()


def test_driver_selection_replay_is_refused() -> None:
    ledger = SpineDriverSelectionLedger()
    try:
        ledger.select(
            consumption=_consumption(),
            consumption_verify=_consumption_verify(),
            now=NOW,
        )
        with pytest.raises(SpineDriverSelectionError, match="replay refused"):
            ledger.select(
                consumption=_consumption(),
                consumption_verify=_consumption_verify(),
                now=NOW,
            )
        assert ledger.count() == 1
    finally:
        ledger.close()


def test_driver_selection_rejects_unverified_or_unsupported_target() -> None:
    ledger = SpineDriverSelectionLedger()
    try:
        bad = _consumption()
        bad["target_driver"] = "motor"
        with pytest.raises(SpineDriverSelectionError, match="unsupported"):
            ledger.select(
                consumption=bad,
                consumption_verify=_consumption_verify(),
                now=NOW,
            )

        verify = _consumption_verify()
        verify["verified"] = False
        with pytest.raises(SpineDriverSelectionError, match="independent consumption"):
            ledger.select(
                consumption=_consumption(),
                consumption_verify=verify,
                now=NOW,
            )
    finally:
        ledger.close()
