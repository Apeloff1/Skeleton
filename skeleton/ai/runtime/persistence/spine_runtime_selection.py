"""Fail-closed runtime-driver selection candidate for the P2 spine.

A live deployment qualification can become a candidate for a later operator
cutover, but this seam never selects a runtime driver, starts a dispatcher, or
activates Mongo persistence.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from skeleton.persistence.spine_motor_plan import SpineMotorPlan
from skeleton.persistence.spine_pymongo_async_qualification_verify import (
    SpinePyMongoAsyncQualificationVerify,
)


class SpineRuntimeSelectionError(RuntimeError):
    """Runtime selection evidence is incomplete, changed, or already activated."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineRuntimeSelection:
    """Turn verified live-driver evidence into a non-selecting candidate card."""

    def candidate(
        self,
        *,
        qualification: dict[str, Any],
        dispatch_guard: dict[str, Any],
    ) -> dict[str, Any]:
        if (
            not isinstance(qualification, dict)
            or qualification.get("kind") != "spine_pymongo_async_live_qualification"
            or qualification.get("qualified") is not True
        ):
            raise SpineRuntimeSelectionError("live qualification is missing or invalid")

        if qualification.get("supported_async_driver") is not True:
            raise SpineRuntimeSelectionError("unsupported async driver")
        if qualification.get("deployment_driver_imported") is not True:
            raise SpineRuntimeSelectionError("deployment driver was not imported")
        if qualification.get("deployment_driver_connected") is not True:
            raise SpineRuntimeSelectionError("deployment driver was not connected")
        if qualification.get("core_driver_imported") is not False:
            raise SpineRuntimeSelectionError("core persistence imported a driver")
        if qualification.get("runtime_driver_selected") is not False:
            raise SpineRuntimeSelectionError("runtime driver was already selected")
        if qualification.get("runtime_activated") is not False:
            raise SpineRuntimeSelectionError("runtime was already activated")
        if qualification.get("live_motor") is not False:
            raise SpineRuntimeSelectionError("legacy Motor authority is not dark")
        if qualification.get("bootstrap_replay_equivalent") is not True:
            raise SpineRuntimeSelectionError("bootstrap replay is not equivalent")
        if qualification.get("indexes_planned") != 3 or qualification.get("indexes_applied") != 3:
            raise SpineRuntimeSelectionError("canonical index qualification is incomplete")

        plan = SpineMotorPlan().card()
        if qualification.get("plan_digest") != plan["digest"]:
            raise SpineRuntimeSelectionError("runtime selection plan digest mismatch")
        for name in (
            "digest",
            "driver_receipt_digest",
            "preflight_digest",
            "bootstrap_digest",
        ):
            value = qualification.get(name)
            if not isinstance(value, str) or len(value) != 64:
                raise SpineRuntimeSelectionError(f"invalid qualification digest: {name}")

        try:
            qualification_verified = (
                SpinePyMongoAsyncQualificationVerify().verify(qualification)
            )
        except Exception as exc:
            raise SpineRuntimeSelectionError(
                "live qualification independent verification failed"
            ) from exc
        if (
            qualification_verified.get("qualification_digest")
            != qualification.get("digest")
        ):
            raise SpineRuntimeSelectionError(
                "live qualification digest verification changed"
            )

        if (
            not isinstance(dispatch_guard, dict)
            or dispatch_guard.get("kind") != "spine_dispatch_guard"
            or dispatch_guard.get("same") is not True
        ):
            raise SpineRuntimeSelectionError("dispatcher identity proof is missing")
        if dispatch_guard.get("called") is not False:
            raise SpineRuntimeSelectionError("dispatcher was called during selection")
        if dispatch_guard.get("runtime_replaced") is not False:
            raise SpineRuntimeSelectionError("runtime dispatcher was replaced")

        evidence = {
            "qualification_digest": qualification["digest"],
            "driver_receipt_digest": qualification["driver_receipt_digest"],
            "preflight_digest": qualification["preflight_digest"],
            "bootstrap_digest": qualification["bootstrap_digest"],
            "plan_digest": qualification["plan_digest"],
            "index_names": list(qualification["index_names"]),
            "driver_distribution": qualification.get("driver_distribution"),
            "driver_version": qualification.get("driver_version"),
            "driver_class": qualification.get("driver_class"),
            "candidate_driver": "pymongo-async",
            "indexes_applied": qualification["indexes_applied"],
            "dispatcher_identity_stable": True,
            "dispatcher_called": False,
            "runtime_driver_selected": False,
            "selection_authorized": False,
            "runtime_activated": False,
        }
        return {
            "kind": "spine_runtime_selection_candidate",
            "hit": False,
            "law": "qualified-driver-does-not-self-select",
            "citation": "VOL-134",
            **evidence,
            "digest": _digest(evidence),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
