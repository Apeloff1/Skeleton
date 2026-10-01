from __future__ import annotations

import copy

import pytest

from skeleton.persistence.spine_cutover_rehearsal import (
    SpineCutoverRehearsal,
    SpineCutoverRehearsalError,
)
from skeleton.persistence.spine_cutover_rehearsal_verify import (
    SpineCutoverRehearsalVerify,
    SpineCutoverRehearsalVerifyError,
)


def _candidate() -> dict[str, object]:
    return {
        "kind": "spine_runtime_selection_candidate",
        "digest": "a" * 64,
        "runtime_driver_selected": False,
        "selection_authorized": False,
        "runtime_activated": False,
    }


def _selection_verify() -> dict[str, object]:
    return {
        "kind": "spine_runtime_selection_verify",
        "candidate_digest": "a" * 64,
        "verified": True,
        "runtime_driver_selected": False,
        "selection_authorized": False,
        "runtime_activated": False,
    }


def _cutover() -> dict[str, object]:
    return {
        "kind": "spine_cutover",
        "hit": True,
        "pending": 0,
        "published": 1,
        "sqlite_epoch": 0,
        "mongo_epoch": 0,
        "apply_refused": True,
        "applied": 0,
    }


def test_green_preconditions_rehearse_without_switching() -> None:
    card = SpineCutoverRehearsal().rehearse(
        candidate=_candidate(),
        selection_verify=_selection_verify(),
        cutover=_cutover(),
        chain={"match": True},
    )
    verified = SpineCutoverRehearsalVerify().verify(card)

    assert card["preconditions_green"] is True
    assert card["switch_refused"] is True
    assert card["switch_reason"] == "switch-not-landed"
    assert card["applied_fence"] is False
    assert card["runtime_driver_selected"] is False
    assert card["selection_authorized"] is False
    assert card["runtime_activated"] is False
    assert len(card["digest"]) == 64
    assert verified["verified"] is True
    assert verified["switch_refused"] is True


@pytest.mark.parametrize(
    ("target", "field", "value", "match"),
    [
        ("candidate", "runtime_driver_selected", True, "already selected"),
        ("candidate", "selection_authorized", True, "already authorized"),
        ("selection", "verified", False, "verification"),
        ("cutover", "hit", False, "not green"),
        ("cutover", "applied", 1, "not closed"),
        ("cutover", "apply_refused", False, "refusal proof"),
        ("chain", "match", False, "chain prerequisite"),
    ],
)
def test_rehearsal_fails_closed_on_invalid_precondition(
    target: str,
    field: str,
    value: object,
    match: str,
) -> None:
    candidate = _candidate()
    selection = _selection_verify()
    cutover = _cutover()
    chain: dict[str, object] = {"match": True}
    cards = {
        "candidate": candidate,
        "selection": selection,
        "cutover": cutover,
        "chain": chain,
    }
    cards[target][field] = value

    with pytest.raises(SpineCutoverRehearsalError, match=match):
        SpineCutoverRehearsal().rehearse(
            candidate=candidate,
            selection_verify=selection,
            cutover=cutover,
            chain=chain,
        )


def test_rehearsal_verifier_rejects_authority_and_digest_tamper() -> None:
    card = SpineCutoverRehearsal().rehearse(
        candidate=_candidate(),
        selection_verify=_selection_verify(),
        cutover=_cutover(),
        chain={"match": True},
    )

    activated = copy.deepcopy(card)
    activated["runtime_activated"] = True
    with pytest.raises(
        SpineCutoverRehearsalVerifyError,
        match="gained runtime authority",
    ):
        SpineCutoverRehearsalVerify().verify(activated)

    tampered = copy.deepcopy(card)
    tampered["published"] = 99
    with pytest.raises(SpineCutoverRehearsalVerifyError, match="digest mismatch"):
        SpineCutoverRehearsalVerify().verify(tampered)
