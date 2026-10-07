from __future__ import annotations

import copy
import hashlib
import json

import pytest

from skeleton.persistence.spine_motor_plan import SpineMotorPlan
from skeleton.persistence.spine_pymongo_async_qualification_verify import (
    SpinePyMongoAsyncQualificationVerify,
    SpinePyMongoAsyncQualificationVerifyError,
)


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _qualification() -> dict[str, object]:
    plan = SpineMotorPlan().card()
    evidence: dict[str, object] = {
        "driver_receipt_digest": "a" * 64,
        "driver_distribution": "pymongo",
        "driver_version": "4.18.2",
        "driver_class": "AsyncMongoClient",
        "plan_digest": plan["digest"],
        "preflight_digest": "b" * 64,
        "bootstrap_digest": "c" * 64,
        "index_names": [row["name"] for row in plan["indexes"]],
        "wire_version_min": 0,
        "wire_version_max": 21,
        "indexes_planned": plan["count"],
        "indexes_applied": plan["count"],
        "bootstrap_replay_equivalent": True,
        "supported_async_driver": True,
        "deployment_driver_imported": True,
        "deployment_driver_connected": True,
        "core_driver_imported": False,
        "runtime_driver_selected": False,
        "runtime_activated": False,
        "live_motor": False,
    }
    return {
        "schema_version": 1,
        "kind": "spine_pymongo_async_live_qualification",
        "law": "live-driver-qualification-is-not-runtime-activation",
        **evidence,
        "digest": _digest(evidence),
        "qualified": True,
        "completion_checkbox": False,
        "implementation_signature": False,
        "verification_signature": False,
    }


def test_live_pymongo_qualification_is_independently_verified() -> None:
    card = _qualification()
    verified = SpinePyMongoAsyncQualificationVerify().verify(card)

    assert verified["verified"] is True
    assert verified["qualification_digest"] == card["digest"]
    assert verified["bootstrap_digest"] == card["bootstrap_digest"]
    assert verified["index_names"] == card["index_names"]
    assert verified["runtime_driver_selected"] is False
    assert verified["runtime_activated"] is False


def test_verifier_rejects_index_identity_tamper() -> None:
    card = _qualification()
    card["index_names"] = ["wrong"]

    with pytest.raises(
        SpinePyMongoAsyncQualificationVerifyError,
        match="index identities changed",
    ):
        SpinePyMongoAsyncQualificationVerify().verify(card)


def test_verifier_rejects_digest_tamper() -> None:
    card = _qualification()
    card["digest"] = "f" * 64

    with pytest.raises(
        SpinePyMongoAsyncQualificationVerifyError,
        match="qualification digest mismatch",
    ):
        SpinePyMongoAsyncQualificationVerify().verify(card)


def test_verifier_rejects_runtime_authority_tamper() -> None:
    card = copy.deepcopy(_qualification())
    card["runtime_driver_selected"] = True

    with pytest.raises(
        SpinePyMongoAsyncQualificationVerifyError,
        match="authority invariant changed",
    ):
        SpinePyMongoAsyncQualificationVerify().verify(card)
