"""Durable runtime-driver selection state for P2.

A verified, consumed selection permit may persist the selected driver target.
This is control-plane state only: it does not import PyMongo, replace a runtime
object, start a dispatcher, advance a fence, or activate runtime.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any


class SpineDriverSelectionError(RuntimeError):
    """Driver selection state rejected incomplete, replayed, or invalid evidence."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SpineDriverSelectionLedger:
    """Persist exactly one selected driver per consumed permit."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(str(path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_driver_selection (
                selection_id TEXT PRIMARY KEY,
                consumption_digest TEXT NOT NULL UNIQUE,
                permit_id TEXT NOT NULL UNIQUE,
                target_driver TEXT NOT NULL,
                selected_at TEXT NOT NULL,
                payload_digest TEXT NOT NULL,
                activated INTEGER NOT NULL DEFAULT 0 CHECK(activated IN (0, 1))
            )
            """
        )
        self._connection.commit()

    def select(
        self,
        *,
        consumption: dict[str, Any],
        consumption_verify: dict[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if (
            not isinstance(consumption, dict)
            or consumption.get("kind") != "spine_selection_consumption"
            or consumption.get("selection_authorized") is not True
            or consumption.get("permit_consumed") is not True
        ):
            raise SpineDriverSelectionError("verified consumed selection permit is required")
        if consumption.get("runtime_driver_selected") is not False:
            raise SpineDriverSelectionError("runtime driver was already selected")
        if consumption.get("runtime_activated") is not False:
            raise SpineDriverSelectionError("runtime was already activated")
        if consumption.get("target_driver") != "pymongo-async":
            raise SpineDriverSelectionError("unsupported runtime driver target")

        consumption_digest = consumption.get("digest")
        permit_id = consumption.get("permit_id")
        if not isinstance(consumption_digest, str) or len(consumption_digest) != 64:
            raise SpineDriverSelectionError("consumption digest is invalid")
        if not isinstance(permit_id, str) or len(permit_id) != 64:
            raise SpineDriverSelectionError("permit identity is invalid")

        if (
            not isinstance(consumption_verify, dict)
            or consumption_verify.get("kind") != "spine_selection_consumption_verify"
            or consumption_verify.get("verified") is not True
            or consumption_verify.get("consumption_digest") != consumption_digest
            or consumption_verify.get("permit_id") != permit_id
            or consumption_verify.get("selection_authorized") is not True
            or consumption_verify.get("permit_consumed") is not True
            or consumption_verify.get("runtime_driver_selected") is not False
            or consumption_verify.get("runtime_activated") is not False
        ):
            raise SpineDriverSelectionError("independent consumption verification is required")

        instant = now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineDriverSelectionError("now must be timezone-aware")
        instant = instant.astimezone(timezone.utc)

        selection_id = hashlib.sha256(
            f"{consumption_digest}|{permit_id}|pymongo-async".encode("utf-8")
        ).hexdigest()
        evidence = {
            "selection_id": selection_id,
            "consumption_digest": consumption_digest,
            "permit_id": permit_id,
            "target_driver": "pymongo-async",
            "selected_at": instant.isoformat(),
            "selection_authorized": True,
            "permit_consumed": True,
            "runtime_driver_selected": True,
            "runtime_object_replaced": False,
            "dispatcher_started": False,
            "runtime_activated": False,
        }
        payload_digest = _digest(evidence)

        try:
            self._connection.execute(
                """
                INSERT INTO spine_driver_selection(
                    selection_id, consumption_digest, permit_id, target_driver,
                    selected_at, payload_digest, activated
                ) VALUES (?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    selection_id,
                    consumption_digest,
                    permit_id,
                    "pymongo-async",
                    instant.isoformat(),
                    payload_digest,
                ),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as exc:
            raise SpineDriverSelectionError("driver selection replay refused") from exc

        return {
            "kind": "spine_driver_selection",
            "hit": False,
            "law": "consumed-permit-selects-driver-state-not-runtime-activation",
            "citation": "VOL-134",
            **evidence,
            "digest": payload_digest,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def count(self) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) AS n FROM spine_driver_selection"
        ).fetchone()
        return int(row["n"])

    def close(self) -> None:
        self._connection.close()
