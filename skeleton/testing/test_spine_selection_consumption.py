from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from skeleton.persistence.spine_selection_permit import (
    SpineSelectionPermitError,
    SpineSelectionPermitLedger,
)
from skeleton.persistence.spine_selection_permit_verify import SpineSelectionPermitVerify
from skeleton.persistence.spine_selection_consumption_verify import (
    SpineSelectionConsumptionVerify,
)


NOW = datetime(2026, 10, 1, 16, 5, tzinfo=timezone.utc)


def _effectiveness() -> dict[str, object]:
    return {
        "kind": "spine_cutover_effectiveness",
        "digest": "e" * 64,
        "authorization_digest": "a" * 64,
        "effectiveness_receipt": {
            "one_time_nonce": "n" * 64,
            "expires_at": (NOW + timedelta(minutes=5)).isoformat(),
        },
        "external_change_control_authenticated": True,
        "authorization_effective": True,
        "selection_authorized": False,
        "runtime_driver_selected": False,
        "runtime_activated": False,
    }


def _effectiveness_verify() -> dict[str, object]:
    return {
        "kind": "spine_cutover_effectiveness_verify",
        "effectiveness_digest": "e" * 64,
        "authorization_digest": "a" * 64,
        "one_time_nonce": "n" * 64,
        "verified": True,
        "authorization_effective": True,
        "selection_authorized": False,
        "runtime_driver_selected": False,
        "runtime_activated": False,
    }


def test_selection_permit_is_consumed_once_without_selecting_runtime() -> None:
    ledger = SpineSelectionPermitLedger()
    try:
        permit = ledger.issue(
            effectiveness=_effectiveness(),
            effectiveness_verify=_effectiveness_verify(),
            now=NOW,
        )
        permit_verify = SpineSelectionPermitVerify().verify(permit)
        consumed = ledger.consume(
            permit=permit,
            permit_verify=permit_verify,
            now=NOW + timedelta(seconds=1),
        )
        verified = SpineSelectionConsumptionVerify().verify(consumed)

        assert ledger.count() == 1
        assert ledger.consumed_count() == 1
        assert consumed["selection_authorized"] is True
        assert consumed["permit_consumed"] is True
        assert consumed["runtime_driver_selected"] is False
        assert consumed["runtime_activated"] is False
        assert verified["verified"] is True

        with pytest.raises(SpineSelectionPermitError, match="replay refused"):
            ledger.consume(
                permit=permit,
                permit_verify=permit_verify,
                now=NOW + timedelta(seconds=2),
            )
    finally:
        ledger.close()


def test_selection_permit_cannot_be_consumed_after_validity_window() -> None:
    ledger = SpineSelectionPermitLedger()
    try:
        permit = ledger.issue(
            effectiveness=_effectiveness(),
            effectiveness_verify=_effectiveness_verify(),
            now=NOW,
        )
        permit_verify = SpineSelectionPermitVerify().verify(permit)
        with pytest.raises(SpineSelectionPermitError, match="expired before consumption"):
            ledger.consume(
                permit=permit,
                permit_verify=permit_verify,
                now=NOW + timedelta(minutes=6),
            )
        assert ledger.consumed_count() == 0
    finally:
        ledger.close()
