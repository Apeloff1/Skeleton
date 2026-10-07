"""Non-activating async-Mongo deployment preflight for the P2 spine.

The deployment supplies a database-like object. Core imports no Mongo driver,
performs only read/command protocol probes, and never grants live authority.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from typing import Any

from skeleton.persistence.spine_motor_plan import SpineMotorPlan


class SpineMotorPreflightError(RuntimeError):
    """The injected database surface failed protocol qualification."""


async def _resolve(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


class SpineMotorPreflight:
    """Probe ping/hello and canonical collection protocol without activation."""

    async def probe(self, database: Any) -> dict[str, Any]:
        command = getattr(database, "command", None)
        get_collection = getattr(database, "get_collection", None)
        if not callable(command):
            raise SpineMotorPreflightError("database does not expose command")
        if not callable(get_collection):
            raise SpineMotorPreflightError("database does not expose get_collection")

        try:
            ping = await _resolve(command("ping"))
            hello = await _resolve(command("hello"))
        except Exception as exc:
            raise SpineMotorPreflightError("database command probe failed") from exc

        if not isinstance(ping, dict) or ping.get("ok") != 1:
            raise SpineMotorPreflightError("database ping did not return ok=1")
        if not isinstance(hello, dict) or hello.get("ok") != 1:
            raise SpineMotorPreflightError("database hello did not return ok=1")

        minimum = hello.get("minWireVersion")
        maximum = hello.get("maxWireVersion")
        if (
            isinstance(minimum, bool)
            or isinstance(maximum, bool)
            or not isinstance(minimum, int)
            or not isinstance(maximum, int)
            or minimum < 0
            or maximum < minimum
        ):
            raise SpineMotorPreflightError("database wire-version range is invalid")

        plan = SpineMotorPlan().card()
        collections: list[str] = []
        for row in plan["indexes"]:
            name = row["collection"]
            try:
                target = get_collection(name)
            except Exception as exc:
                raise SpineMotorPreflightError(
                    f"collection lookup failed for {name}"
                ) from exc
            if inspect.isawaitable(target):
                raise SpineMotorPreflightError(
                    f"collection lookup for {name} must be synchronous"
                )
            if not callable(getattr(target, "create_index", None)):
                raise SpineMotorPreflightError(
                    f"collection {name} does not expose create_index"
                )
            collections.append(name)

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
        return {
            "kind": "spine_motor_preflight",
            "hit": True,
            "law": "deployment-protocol-qualified-without-activation",
            "citation": "VOL-134",
            **evidence,
            "digest": digest,
            "protocol_qualified": True,
            "driver_imported": False,
            "live_motor": False,
            "activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
