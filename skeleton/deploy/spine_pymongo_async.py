"""Supported PyMongo Async deployment adapter for the P2 persistence spine.

This module is deliberately outside skeleton.persistence. Core persistence
remains driver-injected and imports neither PyMongo nor Motor.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import re
from typing import Any

from pymongo import AsyncMongoClient
from pymongo.server_api import ServerApi


MIN_PYMONGO_ASYNC = (4, 13)


class SpinePyMongoAsyncAdapterError(RuntimeError):
    """The supported async Mongo deployment adapter could not be qualified."""


def _version_tuple(raw: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", raw)
    if not parts:
        raise SpinePyMongoAsyncAdapterError("PyMongo version is not numeric")
    return tuple(int(part) for part in parts[:3])


def driver_receipt() -> dict[str, Any]:
    """Return deterministic package/API identity without connecting to MongoDB."""
    try:
        driver_version = version("pymongo")
    except PackageNotFoundError as exc:
        raise SpinePyMongoAsyncAdapterError("PyMongo distribution is unavailable") from exc

    parsed = _version_tuple(driver_version)
    if parsed < MIN_PYMONGO_ASYNC:
        raise SpinePyMongoAsyncAdapterError(
            "PyMongo Async requires pymongo>=4.13 for this deployment lane"
        )

    evidence = {
        "driver_distribution": "pymongo",
        "driver_version": driver_version,
        "driver_class": AsyncMongoClient.__name__,
        "driver_module": AsyncMongoClient.__module__,
        "minimum_version": ".".join(str(part) for part in MIN_PYMONGO_ASYNC),
        "stable_api": "1",
        "supported_async_driver": True,
        "motor_dependency": False,
        "deployment_driver_imported": True,
        "core_driver_imported": False,
        "runtime_activated": False,
    }
    canonical = json.dumps(
        evidence,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return {
        "kind": "spine_pymongo_async_driver_receipt",
        "law": "supported-driver-import-is-deployment-only",
        **evidence,
        "digest": hashlib.sha256(canonical).hexdigest(),
        "completion_checkbox": False,
        "implementation_signature": False,
        "verification_signature": False,
    }


@dataclass(slots=True)
class SpinePyMongoAsyncSession:
    """Own a deployment driver/client without implying runtime activation."""

    client: AsyncMongoClient
    database: Any
    receipt: dict[str, Any]

    async def close(self) -> None:
        await self.client.close()


class SpinePyMongoAsyncAdapter:
    """Construct the supported async driver behind the deployment boundary."""

    def open(
        self,
        *,
        uri: str,
        database_name: str,
        server_selection_timeout_ms: int = 5000,
    ) -> SpinePyMongoAsyncSession:
        if not isinstance(uri, str) or not uri.strip():
            raise SpinePyMongoAsyncAdapterError("Mongo URI must be non-empty text")
        if not isinstance(database_name, str) or not database_name.strip():
            raise SpinePyMongoAsyncAdapterError("database name must be non-empty text")
        if (
            isinstance(server_selection_timeout_ms, bool)
            or not isinstance(server_selection_timeout_ms, int)
            or server_selection_timeout_ms < 1
        ):
            raise SpinePyMongoAsyncAdapterError(
                "server selection timeout must be a positive integer"
            )

        receipt = driver_receipt()
        client = AsyncMongoClient(
            uri,
            server_api=ServerApi("1"),
            serverSelectionTimeoutMS=server_selection_timeout_ms,
        )
        database = client.get_database(database_name)
        return SpinePyMongoAsyncSession(
            client=client,
            database=database,
            receipt=receipt,
        )
