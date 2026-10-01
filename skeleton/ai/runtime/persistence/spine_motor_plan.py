"""Deterministic async-Mongo bootstrap plan for the P2 spine.

The plan derives only from the canonical spine index declarations. It imports
no live Mongo driver and grants no runtime activation or maturity authority.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from skeleton.persistence.spine_index import INDEXES


class SpineMotorPlanError(RuntimeError):
    """Motor bootstrap plan could not be constructed."""


class SpineMotorPlan:
    """Render a deterministic, content-addressed index bootstrap plan."""

    def card(self) -> dict[str, Any]:
        specs: list[dict[str, Any]] = []
        names: set[str] = set()
        for collection, keys, unique in INDEXES:
            if not isinstance(collection, str) or not collection.strip():
                raise SpineMotorPlanError("collection name must be non-empty text")
            if collection in names:
                raise SpineMotorPlanError("duplicate collection in index plan")
            names.add(collection)
            if not isinstance(keys, list) or not keys:
                raise SpineMotorPlanError("index keys must be a non-empty list")
            normalized_keys: list[list[Any]] = []
            for key in keys:
                if (
                    not isinstance(key, tuple)
                    or len(key) != 2
                    or not isinstance(key[0], str)
                    or not key[0].strip()
                    or isinstance(key[1], bool)
                    or not isinstance(key[1], int)
                ):
                    raise SpineMotorPlanError("invalid index key declaration")
                normalized_keys.append([key[0], key[1]])
            specs.append(
                {
                    "collection": collection,
                    "keys": normalized_keys,
                    "unique": bool(unique),
                }
            )
        canonical = json.dumps(
            specs,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return {
            "kind": "spine_motor_plan",
            "hit": True,
            "law": "driver-injected-bootstrap-plan",
            "citation": "VOL-134",
            "indexes": specs,
            "count": len(specs),
            "digest": digest,
            "live_motor": False,
            "driver_imported": False,
            "activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
