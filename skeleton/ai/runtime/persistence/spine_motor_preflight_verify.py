"""Independent verification for P2 async-Mongo deployment preflight evidence."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from skeleton.persistence.spine_motor_plan import SpineMotorPlan


class SpineMotorPreflightVerifyError(RuntimeError):
    """Preflight evidence is incomplete, changed, or gained authority."""


class SpineMotorPreflightVerify:
    """Recompute preflight identity without importing a Mongo driver."""

    def verify(self, card: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(card, dict) or card.get("kind") != "spine_motor_preflight":
            raise SpineMotorPreflightVerifyError("preflight kind mismatch")
        plan = SpineMotorPlan().card()
        collections = [row["collection"] for row in plan["indexes"]]
        if card.get("plan_digest") != plan["digest"]:
            raise SpineMotorPreflightVerifyError("preflight plan digest mismatch")
        if card.get("collections") != collections:
            raise SpineMotorPreflightVerifyError("preflight collection coverage changed")
        minimum = card.get("min_wire_version")
        maximum = card.get("max_wire_version")
        if (
            isinstance(minimum, bool)
            or isinstance(maximum, bool)
            or not isinstance(minimum, int)
            or not isinstance(maximum, int)
            or minimum < 0
            or maximum < minimum
        ):
            raise SpineMotorPreflightVerifyError("preflight wire-version range is invalid")
        if card.get("ping_ok") is not True or card.get("protocol_qualified") is not True:
            raise SpineMotorPreflightVerifyError("preflight protocol is not qualified")
        for flag in ("driver_imported", "live_motor", "activated"):
            if card.get(flag) is not False:
                raise SpineMotorPreflightVerifyError("preflight gained live authority")

        evidence = {
            "plan_digest": plan["digest"],
            "ping_ok": True,
            "min_wire_version": minimum,
            "max_wire_version": maximum,
            "collections": collections,
        }
        canonical = json.dumps(
            evidence,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        if card.get("digest") != digest:
            raise SpineMotorPreflightVerifyError("preflight digest mismatch")

        return {
            "kind": "spine_motor_preflight_verify",
            "hit": True,
            "law": "preflight-verification-does-not-activate",
            "citation": "VOL-134",
            "digest": digest,
            "plan_digest": plan["digest"],
            "verified": True,
            "protocol_qualified": True,
            "driver_imported": False,
            "live_motor": False,
            "activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
