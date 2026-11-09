"""Deployment binder for spine indexes.

Calls create_index only when the injected collection has that method. Does
not import Motor. A missing method is a skip, not a live bootstrap.
"""

from __future__ import annotations

from typing import Any

from skeleton.persistence.spine_index import INDEXES


class SpineIndexBindError(RuntimeError):
    """Index bind rejected its inputs. Not a maturity signal."""


class SpineIndexBind:
    """Apply the declared indexes to injected collections."""

    def bind(self, collections: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(collections, dict):
            raise SpineIndexBindError("collections must be a dict")
        created = 0
        skipped = 0
        missing = 0
        for name, keys, unique in INDEXES:
            target = collections.get(name)
            if target is None:
                missing += 1
                continue
            create = getattr(target, "create_index", None)
            if not callable(create):
                skipped += 1
                continue
            create(keys, unique=unique)
            created += 1
        return {
            "kind": "spine_index_bind",
            "hit": missing == 0,
            "law": "create-index-only-when-present",
            "citation": "VOL-134",
            "created": created,
            "skipped": skipped,
            "missing": missing,
            "live_motor": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
