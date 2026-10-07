"""Independent verifier for live PyMongo Async qualification evidence.

This module imports no Mongo driver. It reconstructs the exact qualification
digest from driver identity, protocol/bootstrap evidence, deterministic index
identities, and dark runtime-authority flags.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from skeleton.persistence.spine_motor_plan import SpineMotorPlan


class SpinePyMongoAsyncQualificationVerifyError(RuntimeError):
    """Live PyMongo Async qualification verification failed closed."""


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_MINIMUM_VERSION = (4, 13)


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _version_tuple(value: object) -> tuple[int, ...]:
    if not isinstance(value, str) or not value.strip():
        raise SpinePyMongoAsyncQualificationVerifyError(
            "driver version is missing"
        )
    parts = re.findall(r"\d+", value)
    if not parts:
        raise SpinePyMongoAsyncQualificationVerifyError(
            "driver version is not numeric"
        )
    return tuple(int(part) for part in parts[:3])


class SpinePyMongoAsyncQualificationVerify:
    """Reconstruct live qualification without importing PyMongo or Motor."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if (
            not isinstance(card, dict)
            or card.get("schema_version") != 1
            or card.get("kind") != "spine_pymongo_async_live_qualification"
            or card.get("qualified") is not True
        ):
            raise SpinePyMongoAsyncQualificationVerifyError(
                "live PyMongo qualification kind or status mismatch"
            )
        if card.get("law") != "live-driver-qualification-is-not-runtime-activation":
            raise SpinePyMongoAsyncQualificationVerifyError(
                "live PyMongo qualification law changed"
            )

        plan = SpineMotorPlan().card()
        expected_names = [row["name"] for row in plan["indexes"]]
        if card.get("plan_digest") != plan["digest"]:
            raise SpinePyMongoAsyncQualificationVerifyError(
                "live PyMongo plan digest mismatch"
            )
        if card.get("index_names") != expected_names:
            raise SpinePyMongoAsyncQualificationVerifyError(
                "live PyMongo index identities changed"
            )
        if card.get("indexes_planned") != plan["count"]:
            raise SpinePyMongoAsyncQualificationVerifyError(
                "live PyMongo planned index count changed"
            )
        if card.get("indexes_applied") != plan["count"]:
            raise SpinePyMongoAsyncQualificationVerifyError(
                "live PyMongo applied index count changed"
            )

        if card.get("driver_distribution") != "pymongo":
            raise SpinePyMongoAsyncQualificationVerifyError(
                "live PyMongo driver distribution changed"
            )
        if card.get("driver_class") != "AsyncMongoClient":
            raise SpinePyMongoAsyncQualificationVerifyError(
                "live PyMongo driver class changed"
            )
        if _version_tuple(card.get("driver_version")) < _MINIMUM_VERSION:
            raise SpinePyMongoAsyncQualificationVerifyError(
                "live PyMongo driver version is below supported minimum"
            )

        for name in (
            "driver_receipt_digest",
            "preflight_digest",
            "bootstrap_digest",
            "digest",
        ):
            value = card.get(name)
            if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
                raise SpinePyMongoAsyncQualificationVerifyError(
                    f"invalid live PyMongo digest: {name}"
                )

        minimum = card.get("wire_version_min")
        maximum = card.get("wire_version_max")
        if (
            isinstance(minimum, bool)
            or not isinstance(minimum, int)
            or minimum < 0
            or isinstance(maximum, bool)
            or not isinstance(maximum, int)
            or maximum < minimum
        ):
            raise SpinePyMongoAsyncQualificationVerifyError(
                "live PyMongo wire-version range is invalid"
            )

        for field in (
            "bootstrap_replay_equivalent",
            "supported_async_driver",
            "deployment_driver_imported",
            "deployment_driver_connected",
        ):
            if card.get(field) is not True:
                raise SpinePyMongoAsyncQualificationVerifyError(
                    f"live PyMongo positive invariant missing: {field}"
                )
        for field in (
            "core_driver_imported",
            "runtime_driver_selected",
            "runtime_activated",
            "live_motor",
            "completion_checkbox",
            "implementation_signature",
            "verification_signature",
        ):
            if card.get(field) is not False:
                raise SpinePyMongoAsyncQualificationVerifyError(
                    f"live PyMongo authority invariant changed: {field}"
                )

        evidence = {
            "driver_receipt_digest": card["driver_receipt_digest"],
            "driver_distribution": card["driver_distribution"],
            "driver_version": card["driver_version"],
            "driver_class": card["driver_class"],
            "plan_digest": card["plan_digest"],
            "preflight_digest": card["preflight_digest"],
            "bootstrap_digest": card["bootstrap_digest"],
            "index_names": list(card["index_names"]),
            "wire_version_min": minimum,
            "wire_version_max": maximum,
            "indexes_planned": card["indexes_planned"],
            "indexes_applied": card["indexes_applied"],
            "bootstrap_replay_equivalent": True,
            "supported_async_driver": True,
            "deployment_driver_imported": True,
            "deployment_driver_connected": True,
            "core_driver_imported": False,
            "runtime_driver_selected": False,
            "runtime_activated": False,
            "live_motor": False,
        }
        digest = _digest(evidence)
        if card.get("digest") != digest:
            raise SpinePyMongoAsyncQualificationVerifyError(
                "live PyMongo qualification digest mismatch"
            )

        return {
            "kind": "spine_pymongo_async_live_qualification_verify",
            "hit": True,
            "law": "live-driver-qualification-verification-does-not-select-runtime",
            "citation": "VOL-134",
            "qualification_digest": digest,
            "bootstrap_digest": card["bootstrap_digest"],
            "plan_digest": plan["digest"],
            "index_names": expected_names,
            "verified": True,
            "runtime_driver_selected": False,
            "selection_authorized": False,
            "runtime_activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
