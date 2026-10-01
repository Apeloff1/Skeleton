"""Fail-closed activation eligibility gate for the P2 runtime spine.

This seam joins durable selected-driver state, independent verification, a live
PyMongo Async qualification receipt, and a stable dispatcher identity proof.
It may declare activation eligible. It never imports the driver, replaces the
runtime object, starts the dispatcher, or activates runtime.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineRuntimeActivationGateError(RuntimeError):
    """Activation eligibility evidence is incomplete, stale, or unsafe."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineRuntimeActivationGate:
    """Join selection and live-driver proofs without performing activation."""

    def qualify(
        self,
        *,
        selection: dict[str, Any],
        selection_verify: dict[str, Any],
        qualification: dict[str, Any],
        dispatch_guard: dict[str, Any],
    ) -> dict[str, Any]:
        if (
            not isinstance(selection, dict)
            or selection.get("kind") != "spine_driver_selection"
            or selection.get("runtime_driver_selected") is not True
            or selection.get("target_driver") != "pymongo-async"
        ):
            raise SpineRuntimeActivationGateError("verified selected PyMongo driver is required")
        if selection.get("runtime_object_replaced") is not False:
            raise SpineRuntimeActivationGateError("runtime object was already replaced")
        if selection.get("dispatcher_started") is not False:
            raise SpineRuntimeActivationGateError("dispatcher was already started")
        if selection.get("runtime_activated") is not False:
            raise SpineRuntimeActivationGateError("runtime was already activated")
        selection_digest = selection.get("digest")
        if not isinstance(selection_digest, str) or len(selection_digest) != 64:
            raise SpineRuntimeActivationGateError("selection digest is invalid")

        if (
            not isinstance(selection_verify, dict)
            or selection_verify.get("kind") != "spine_driver_selection_verify"
            or selection_verify.get("verified") is not True
            or selection_verify.get("selection_digest") != selection_digest
            or selection_verify.get("runtime_driver_selected") is not True
            or selection_verify.get("runtime_object_replaced") is not False
            or selection_verify.get("dispatcher_started") is not False
            or selection_verify.get("runtime_activated") is not False
        ):
            raise SpineRuntimeActivationGateError("independent driver-selection verification is required")

        if (
            not isinstance(qualification, dict)
            or qualification.get("kind") != "spine_pymongo_async_live_qualification"
            or qualification.get("qualified") is not True
            or qualification.get("driver_distribution") != "pymongo"
            or qualification.get("driver_class") != "AsyncMongoClient"
            or qualification.get("supported_async_driver") is not True
            or qualification.get("deployment_driver_connected") is not True
            or qualification.get("core_driver_imported") is not False
            or qualification.get("bootstrap_replay_equivalent") is not True
            or qualification.get("runtime_activated") is not False
        ):
            raise SpineRuntimeActivationGateError("live PyMongo qualification is incomplete")
        qualification_digest = qualification.get("digest")
        if not isinstance(qualification_digest, str) or len(qualification_digest) != 64:
            raise SpineRuntimeActivationGateError("qualification digest is invalid")

        if (
            not isinstance(dispatch_guard, dict)
            or dispatch_guard.get("kind") != "spine_dispatch_guard"
            or dispatch_guard.get("same") is not True
            or dispatch_guard.get("called") is not False
            or dispatch_guard.get("runtime_replaced") is not False
        ):
            raise SpineRuntimeActivationGateError("stable untouched dispatcher identity is required")

        evidence = {
            "selection_digest": selection_digest,
            "qualification_digest": qualification_digest,
            "target_driver": "pymongo-async",
            "driver_distribution": "pymongo",
            "driver_class": "AsyncMongoClient",
            "deployment_driver_connected": True,
            "bootstrap_replay_equivalent": True,
            "dispatcher_identity_stable": True,
            "dispatcher_called": False,
            "activation_eligible": True,
            "runtime_driver_selected": True,
            "runtime_object_replaced": False,
            "dispatcher_started": False,
            "runtime_activated": False,
        }
        return {
            "kind": "spine_runtime_activation_gate",
            "hit": False,
            "law": "activation-eligibility-does-not-activate-runtime",
            "citation": "VOL-134",
            **evidence,
            "digest": _digest(evidence),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
