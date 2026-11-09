from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest

from skeleton.persistence.spine_selection_permit import (
    SpineSelectionPermitError,
    SpineSelectionPermitLedger,
)
from skeleton.persistence.spine_selection_permit_verify import (
    SpineSelectionPermitVerify,
    SpineSelectionPermitVerifyError,
)


NOW = datetime(2026, 10, 1, 16, 5, tzinfo=timezone.utc)


def _effectiveness(
    *,
    effect_digest: str = "e" * 64,
    auth_digest: str = "a" * 64,
    nonce: str = "n" * 64,
) -> dict[str, object]:
    return {
        "kind": "spine_cutover_effectiveness",
        "digest": effect_digest,
        "authorization_digest": auth_digest,
        "effectiveness_receipt": {
            "one_time_nonce": nonce,
            "expires_at": (NOW + timedelta(minutes=5)).isoformat(),
        },
        "external_change_control_authenticated": True,
        "authorization_effective": True,
        "selection_authorized": False,
        "runtime_driver_selected": False,
        "runtime_activated": False,
    }


def _verify(
    *,
    effect_digest: str = "e" * 64,
    auth_digest: str = "a" * 64,
    nonce: str = "n" * 64,
) -> dict[str, object]:
    return {
        "kind": "spine_cutover_effectiveness_verify",
        "effectiveness_digest": effect_digest,
        "authorization_digest": auth_digest,
        "one_time_nonce": nonce,
        "verified": True,
        "authorization_effective": True,
        "selection_authorized": False,
        "runtime_driver_selected": False,
        "runtime_activated": False,
    }


def test_effective_authorization_issues_one_non_activating_selection_permit() -> None:
    ledger = SpineSelectionPermitLedger()
    try:
        card = ledger.issue(
            effectiveness=_effectiveness(),
            effectiveness_verify=_verify(),
            now=NOW,
        )
        verified = SpineSelectionPermitVerify().verify(card)

        assert ledger.count() == 1
        assert card["selection_authorized"] is True
        assert card["permit_consumed"] is False
        assert card["runtime_driver_selected"] is False
        assert card["runtime_activated"] is False
        assert card["target_driver"] == "pymongo-async"
        assert card["permit_valid_until"] == (NOW + timedelta(minutes=5)).isoformat()
        assert len(card["permit_id"]) == 64
        assert len(card["digest"]) == 64
        assert verified["verified"] is True
        assert verified["selection_authorized"] is True
        assert verified["runtime_driver_selected"] is False
    finally:
        ledger.close()


def test_same_effectiveness_or_nonce_cannot_issue_twice() -> None:
    ledger = SpineSelectionPermitLedger()
    try:
        ledger.issue(
            effectiveness=_effectiveness(),
            effectiveness_verify=_verify(),
            now=NOW,
        )
        with pytest.raises(SpineSelectionPermitError, match="replay or nonce reuse"):
            ledger.issue(
                effectiveness=_effectiveness(),
                effectiveness_verify=_verify(),
                now=NOW,
            )

        second = _effectiveness(
            effect_digest="f" * 64,
            auth_digest="b" * 64,
            nonce="n" * 64,
        )
        second_verify = _verify(
            effect_digest="f" * 64,
            auth_digest="b" * 64,
            nonce="n" * 64,
        )
        with pytest.raises(SpineSelectionPermitError, match="replay or nonce reuse"):
            ledger.issue(
                effectiveness=second,
                effectiveness_verify=second_verify,
                now=NOW,
            )
        assert ledger.count() == 1
    finally:
        ledger.close()


def test_selection_permit_rejects_expired_effectiveness_window() -> None:
    ledger = SpineSelectionPermitLedger()
    try:
        effectiveness = _effectiveness()
        effectiveness["effectiveness_receipt"]["expires_at"] = (
            NOW - timedelta(seconds=1)
        ).isoformat()
        with pytest.raises(
            SpineSelectionPermitError,
            match="window expired",
        ):
            ledger.issue(
                effectiveness=effectiveness,
                effectiveness_verify=_verify(),
                now=NOW,
            )
        assert ledger.count() == 0
    finally:
        ledger.close()


def test_selection_permit_rejects_mismatched_independent_verification() -> None:
    ledger = SpineSelectionPermitLedger()
    try:
        bad = _verify(effect_digest="f" * 64)
        with pytest.raises(
            SpineSelectionPermitError,
            match="independent effectiveness verification",
        ):
            ledger.issue(
                effectiveness=_effectiveness(),
                effectiveness_verify=bad,
                now=NOW,
            )
        assert ledger.count() == 0
    finally:
        ledger.close()


def test_selection_permit_verifier_rejects_activation_or_tamper() -> None:
    ledger = SpineSelectionPermitLedger()
    try:
        card = ledger.issue(
            effectiveness=_effectiveness(),
            effectiveness_verify=_verify(),
            now=NOW,
        )
    finally:
        ledger.close()

    selected = copy.deepcopy(card)
    selected["runtime_driver_selected"] = True
    with pytest.raises(
        SpineSelectionPermitVerifyError,
        match="already selected",
    ):
        SpineSelectionPermitVerify().verify(selected)

    tampered = copy.deepcopy(card)
    tampered["issued_at"] = "2026-10-01T17:00:00+00:00"
    with pytest.raises(
        SpineSelectionPermitVerifyError,
        match="digest mismatch",
    ):
        SpineSelectionPermitVerify().verify(tampered)
