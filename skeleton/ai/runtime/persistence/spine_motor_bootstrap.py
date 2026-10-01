"""Driver-injected async Mongo index bootstrap for the P2 spine.

The core module imports no Mongo driver. A deployment supplies collection
objects exposing create_index. Sync and awaitable return values are supported
so tests can model both protocols without activating a live driver.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from typing import Any

from skeleton.persistence.spine_motor_plan import SpineMotorPlan


class SpineMotorBootstrapError(RuntimeError):
    """Injected bootstrap surface is incomplete or failed."""


class SpineMotorBootstrap:
    """Apply the canonical index plan to injected collection objects."""

    async def apply(self, collections: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(collections, dict):
            raise SpineMotorBootstrapError("collections must be a dict")
        plan = SpineMotorPlan().card()
        expected = [row["collection"] for row in plan["indexes"]]
        missing = [name for name in expected if name not in collections]
        if missing:
            raise SpineMotorBootstrapError(
                "missing bootstrap collections: " + ",".join(sorted(missing))
            )

        results: list[dict[str, Any]] = []
        for spec in plan["indexes"]:
            name = spec["collection"]
            target = collections[name]
            create = getattr(target, "create_index", None)
            if not callable(create):
                raise SpineMotorBootstrapError(
                    f"collection {name} does not expose create_index"
                )
            keys = [tuple(item) for item in spec["keys"]]
            try:
                outcome = create(
                    keys,
                    unique=spec["unique"],
                    name=spec["name"],
                )
                if inspect.isawaitable(outcome):
                    outcome = await outcome
            except Exception as exc:
                raise SpineMotorBootstrapError(
                    f"index bootstrap failed for {name}"
                ) from exc
            if not isinstance(outcome, str) or outcome != spec["name"]:
                raise SpineMotorBootstrapError(
                    f"index bootstrap result identity mismatch for {name}"
                )
            results.append(
                {
                    "collection": name,
                    "index_name": spec["name"],
                    "result": outcome,
                    "unique": spec["unique"],
                    "keys": spec["keys"],
                }
            )

        evidence = {
            "plan_digest": plan["digest"],
            "planned": plan["count"],
            "applied": len(results),
            "results": results,
            "missing": 0,
            "failures": 0,
            "bootstrap_exercised": True,
            "live_motor": False,
            "driver_imported": False,
            "activated": False,
        }
        encoded = json.dumps(
            evidence,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return {
            "kind": "spine_motor_bootstrap",
            "hit": len(results) == plan["count"],
            "law": "driver-injected-index-bootstrap",
            "citation": "VOL-134",
            **evidence,
            "digest": hashlib.sha256(encoded).hexdigest(),
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
