"""Independent contract verification for injected async Mongo bootstrap."""

from __future__ import annotations

from typing import Any

from skeleton.persistence.spine_motor_plan import SpineMotorPlan


class SpineMotorBootstrapVerifyError(RuntimeError):
    """Bootstrap evidence failed verification."""


class SpineMotorBootstrapVerify:
    """Verify plan identity, cardinality, result coverage, and dark authority."""

    def verify(self, bootstrap: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(bootstrap, dict) or bootstrap.get("kind") != "spine_motor_bootstrap":
            raise SpineMotorBootstrapVerifyError("bootstrap kind mismatch")
        plan = SpineMotorPlan().card()
        if bootstrap.get("plan_digest") != plan["digest"]:
            raise SpineMotorBootstrapVerifyError("bootstrap plan digest mismatch")
        if bootstrap.get("planned") != plan["count"]:
            raise SpineMotorBootstrapVerifyError("bootstrap planned count mismatch")
        if bootstrap.get("applied") != plan["count"]:
            raise SpineMotorBootstrapVerifyError("bootstrap did not apply every index")
        if bootstrap.get("missing") != 0 or bootstrap.get("failures") != 0:
            raise SpineMotorBootstrapVerifyError("bootstrap reported incomplete work")
        if bootstrap.get("bootstrap_exercised") is not True:
            raise SpineMotorBootstrapVerifyError("bootstrap was not exercised")

        results = bootstrap.get("results")
        if not isinstance(results, list) or len(results) != plan["count"]:
            raise SpineMotorBootstrapVerifyError("bootstrap results are incomplete")
        expected = {row["collection"]: row for row in plan["indexes"]}
        seen: set[str] = set()
        for row in results:
            if not isinstance(row, dict):
                raise SpineMotorBootstrapVerifyError("bootstrap result must be an object")
            name = row.get("collection")
            if name not in expected or name in seen:
                raise SpineMotorBootstrapVerifyError("bootstrap result collection mismatch")
            seen.add(name)
            if row.get("keys") != expected[name]["keys"]:
                raise SpineMotorBootstrapVerifyError("bootstrap result keys changed")
            if row.get("unique") is not expected[name]["unique"]:
                raise SpineMotorBootstrapVerifyError("bootstrap uniqueness changed")
            result = row.get("result")
            if result is not None and not isinstance(result, str):
                raise SpineMotorBootstrapVerifyError("bootstrap result identity is invalid")

        for flag in ("live_motor", "driver_imported", "activated"):
            if bootstrap.get(flag) is not False:
                raise SpineMotorBootstrapVerifyError("bootstrap gained live authority")

        return {
            "kind": "spine_motor_bootstrap_verify",
            "hit": True,
            "law": "bootstrap-verification-does-not-activate",
            "citation": "VOL-134",
            "plan_digest": plan["digest"],
            "verified_indexes": plan["count"],
            "verified": True,
            "live_motor": False,
            "driver_imported": False,
            "activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
