from __future__ import annotations

import copy

import pytest

from skeleton.persistence.spine_dispatch_guard import SpineDispatchGuard
from skeleton.persistence.spine_motor_plan import SpineMotorPlan
from skeleton.persistence.spine_runtime_selection import (
    SpineRuntimeSelection,
    SpineRuntimeSelectionError,
)
from skeleton.persistence.spine_runtime_selection_verify import (
    SpineRuntimeSelectionVerify,
    SpineRuntimeSelectionVerifyError,
)


class _Runtime:
    def start_dispatcher(self) -> bool:
        raise AssertionError("selection must not call the dispatcher")


def _qualification() -> dict[str, object]:
    digest = "a" * 64
    return {
        "kind": "spine_pymongo_async_live_qualification",
        "qualified": True,
        "digest": digest,
        "driver_receipt_digest": "b" * 64,
        "preflight_digest": "c" * 64,
        "plan_digest": SpineMotorPlan().card()["digest"],
        "driver_distribution": "pymongo",
        "driver_version": "4.15.0",
        "driver_class": "AsyncMongoClient",
        "supported_async_driver": True,
        "deployment_driver_imported": True,
        "deployment_driver_connected": True,
        "core_driver_imported": False,
        "indexes_planned": 3,
        "indexes_applied": 3,
        "bootstrap_replay_equivalent": True,
        "runtime_driver_selected": False,
        "runtime_activated": False,
        "live_motor": False,
    }


def _dispatch_card() -> dict[str, object]:
    runtime = _Runtime()
    guard = SpineDispatchGuard()
    return guard.compare(guard.snapshot(runtime), runtime)


def test_live_qualification_becomes_candidate_without_selection() -> None:
    card = SpineRuntimeSelection().candidate(
        qualification=_qualification(),
        dispatch_guard=_dispatch_card(),
    )
    verified = SpineRuntimeSelectionVerify().verify(card)

    assert card["candidate_driver"] == "pymongo-async"
    assert card["dispatcher_identity_stable"] is True
    assert card["dispatcher_called"] is False
    assert card["runtime_driver_selected"] is False
    assert card["selection_authorized"] is False
    assert card["runtime_activated"] is False
    assert len(card["digest"]) == 64
    assert card["completion_checkbox"] is False
    assert verified["verified"] is True
    assert verified["runtime_driver_selected"] is False
    assert verified["selection_authorized"] is False


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("qualified", False, "qualification"),
        ("supported_async_driver", False, "unsupported"),
        ("deployment_driver_connected", False, "not connected"),
        ("core_driver_imported", True, "core persistence"),
        ("runtime_driver_selected", True, "already selected"),
        ("runtime_activated", True, "already activated"),
        ("bootstrap_replay_equivalent", False, "replay"),
        ("indexes_applied", 2, "index qualification"),
    ],
)
def test_candidate_fails_closed_on_invalid_live_evidence(
    field: str,
    value: object,
    match: str,
) -> None:
    qualification = _qualification()
    qualification[field] = value

    with pytest.raises(SpineRuntimeSelectionError, match=match):
        SpineRuntimeSelection().candidate(
            qualification=qualification,
            dispatch_guard=_dispatch_card(),
        )


def test_candidate_fails_closed_when_dispatcher_identity_not_verified() -> None:
    dispatch = _dispatch_card()
    dispatch["same"] = False

    with pytest.raises(SpineRuntimeSelectionError, match="identity proof"):
        SpineRuntimeSelection().candidate(
            qualification=_qualification(),
            dispatch_guard=dispatch,
        )


def test_verifier_rejects_candidate_authority_or_digest_tamper() -> None:
    card = SpineRuntimeSelection().candidate(
        qualification=_qualification(),
        dispatch_guard=_dispatch_card(),
    )

    authorized = copy.deepcopy(card)
    authorized["selection_authorized"] = True
    with pytest.raises(SpineRuntimeSelectionVerifyError, match="gained authority"):
        SpineRuntimeSelectionVerify().verify(authorized)

    tampered = copy.deepcopy(card)
    tampered["qualification_digest"] = "d" * 64
    with pytest.raises(SpineRuntimeSelectionVerifyError, match="digest mismatch"):
        SpineRuntimeSelectionVerify().verify(tampered)
