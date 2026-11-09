"""Drift between the SQLite fence and the Mongo fence.

A mismatch is reported. This module does not advance either fence.
"""

from __future__ import annotations

from typing import Any

from skeleton.persistence.consistency_fence import ConsistencyFenceError, SQLiteConsistencyFence
from skeleton.persistence.mongo_fence import MongoConsistencyFence


class SpineDriftError(RuntimeError):
    """Drift read rejected its inputs. Not a maturity signal."""


class SpineDrift:
    """Compare one resource across the two fences."""

    def __init__(self, sqlite_fence: SQLiteConsistencyFence, mongo_fence: MongoConsistencyFence) -> None:
        if not isinstance(sqlite_fence, SQLiteConsistencyFence):
            raise SpineDriftError("sqlite_fence must be a SQLiteConsistencyFence")
        if not isinstance(mongo_fence, MongoConsistencyFence):
            raise SpineDriftError("mongo_fence must be a MongoConsistencyFence")
        self.sqlite_fence = sqlite_fence
        self.mongo_fence = mongo_fence

    def read(self, *, tenant_id: str, resource_id: str) -> dict[str, Any]:
        sqlite_epoch = self._epoch(self.sqlite_fence, tenant_id, resource_id)
        mongo_epoch = self._mongo_epoch(tenant_id, resource_id)
        return {
            "kind": "spine_drift",
            "hit": sqlite_epoch == mongo_epoch,
            "law": "fence-epoch-parity",
            "citation": "VOL-132",
            "tenant_id": tenant_id,
            "resource_id": resource_id,
            "sqlite_epoch": sqlite_epoch,
            "mongo_epoch": mongo_epoch,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    @staticmethod
    def _epoch(fence: SQLiteConsistencyFence, tenant_id: str, resource_id: str) -> int:
        try:
            return fence.read(tenant_id=tenant_id, resource_id=resource_id).epoch
        except ConsistencyFenceError:
            return 0

    def _mongo_epoch(self, tenant_id: str, resource_id: str) -> int:
        try:
            return self.mongo_fence.read(tenant_id=tenant_id, resource_id=resource_id).epoch
        except ConsistencyFenceError:
            return 0
