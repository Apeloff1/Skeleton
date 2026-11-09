from __future__ import annotations

import copy

import pytest

from skeleton.persistence.spine_runtime_activation_gate import (
    SpineRuntimeActivationGate,
    SpineRuntimeActivationGateError,
)
from skeleton.persistence.spine_runtime_activation_gate_verify import (
    SpineRuntimeActivationGateVerify,
    SpineRuntimeActivationGateVerifyError,
)


def _selection() -> dict[str, object]:
    return {
        "kind": "spine_driver_selection",
        "digest": "s" * 64,
        "target_driver": "pymongo-async",
        "runtime_driver_selected": True,
        "runtime_object_replaced": False,
        "dispatcher_started": False,
        "runtime_activated": False,
    }


def _selection_verify() -> dict[str, object]:
    return {
        "kind": "spine_driver_selection_verify",
        "selection_digest": "s" * 64,
        "verified": True,
        "runtime_driver_selected": True,
        "runtime_object_replaced": False,
        "dispatcher_started": False,
        "runtime_activated": False,
    }


def _qualification() -> dict[str, object]:
    return {
        "kind": "spine_pymongo_async_live_qualification",
        "digest": "q" * 64,
        "qualified": True,
        "driver_distribution": "pymongo",
        "driver_class": "AsyncMongoClient",
        "supported_async_driver": True,
        "deployment_driver_connected": True,
        "core_driver_imported": False,
        "bootstrap_replay_equivalent": True,
        "runtime_activated": False,
    }


def _dispatch_guard() -> dict[str, object]:
    return {
        "kind": "spine_dispatch_guard",
        "same": True,
        "called": False,
        "runtime_replaced": False,
    }


def test_selected_live_driver_can_be_activation_eligible_without_activation() -> None:
    card = SpineRuntimeActivationGate().qualify(
        selection=_selection(),
        selection_verify=_selection_verify(),
        qualification=_qualification(),
        dispatch_guard=_dispatch_guard(),
    )
    verified = SpineRuntimeActivationGateVerify().verify(card)

    assert card["activation_eligible"] is True
    assert card["runtime_driver_selected"] is True
    assert card["runtime_object_replaced"] is False
    assert card["dispatcher_started"] is False
    assert card["runtime_activated"] is False
    assert verified["verified"] is True
    assert verified["activation_eligible"] is True
    assert verified["runtime_activated"] is False


@pytest.mark.parametrize(
    ("target", "field", "value", "match"),
    [
        ("selection", "runtime_driver_selected", False, "selected PyMongo"),
        ("selection", "runtime_object_replaced", True, "already replaced"),
        ("selection_verify", "verified", False, "independent"),
        ("qualification", "qualified", False, "live PyMongo"),
        ("qualification", "deployment_driver_connected", False, "live PyMongo"),
        ("guard", "same", False, "dispatcher"),
        ("guard", "called", True, "dispatcher"),
    ],
)
def test_activation_gate_fails_closed_on_missing_precondition(
    target: str,
    field: str,
    value: object,
    match: str,
) -> None:
    selection = _selection()
    selection_verify = _selection_verify()
    qualification = _qualification()
    guard = _dispatch_guard()
    cards = {
        "selection": selection,
        "selection_verify": selection_verify,
        "qualification": qualification,
        "guard": guard,
    }
    cards[target][field] = value

    with pytest.raises(SpineRuntimeActivationGateError, match=match):
        SpineRuntimeActivationGate().qualify(
            selection=selection,
            selection_verify=selection_verify,
            qualification=qualification,
            dispatch_guard=guard,
        )


def test_activation_gate_verifier_rejects_activation_or_tamper() -> None:
    card = SpineRuntimeActivationGate().qualify(
        selection=_selection(),
        selection_verify=_selection_verify(),
        qualification=_qualification(),
        dispatch_guard=_dispatch_guard(),
    )

    activated = copy.deepcopy(card)
    activated["runtime_activated"] = True
    with pytest.raises(
        SpineRuntimeActivationGateVerifyError,
        match="activated runtime",
    ):
        SpineRuntimeActivationGateVerify().verify(activated)

    tampered = copy.deepcopy(card)
    tampered["qualification_digest"] = "x" * 64
    with pytest.raises(
        SpineRuntimeActivationGateVerifyError,
        match="digest mismatch",
    ):
        SpineRuntimeActivationGateVerify().verify(tampered)
