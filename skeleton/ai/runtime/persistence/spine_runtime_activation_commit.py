"""Durable pre-activation commitment ledger for P2."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any


class SpineRuntimeActivationCommitError(RuntimeError):
    """Activation commitment evidence failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


class SpineRuntimeActivationCommitLedger:
    """Persist one non-activating commitment per consumed activation permit."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self._connection=sqlite3.connect(str(path),check_same_thread=False)
        self._connection.row_factory=sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_runtime_activation_commit (
                commitment_id TEXT PRIMARY KEY,
                consumption_digest TEXT NOT NULL UNIQUE,
                permit_id TEXT NOT NULL UNIQUE,
                target_driver TEXT NOT NULL,
                committed_at TEXT NOT NULL,
                payload_digest TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def commit(
        self,
        *,
        consumption: dict[str, Any],
        consumption_verify: dict[str, Any],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if (
            not isinstance(consumption,dict)
            or consumption.get("kind")!="spine_activation_consumption"
            or consumption.get("activation_authorized") is not True
            or consumption.get("permit_consumed") is not True
            or consumption.get("runtime_driver_selected") is not True
            or consumption.get("runtime_activated") is not False
        ):
            raise SpineRuntimeActivationCommitError("verified activation consumption is required")
        if consumption.get("runtime_object_replaced") is not False or consumption.get("dispatcher_started") is not False:
            raise SpineRuntimeActivationCommitError("activation consumption already changed runtime")
        if consumption.get("target_driver")!="pymongo-async":
            raise SpineRuntimeActivationCommitError("activation target driver changed")
        consumption_digest=consumption.get("digest")
        permit_id=consumption.get("permit_id")
        if not isinstance(consumption_digest,str) or len(consumption_digest)!=64:
            raise SpineRuntimeActivationCommitError("activation consumption digest is invalid")
        if not isinstance(permit_id,str) or len(permit_id)!=64:
            raise SpineRuntimeActivationCommitError("activation permit identity is invalid")
        if (
            not isinstance(consumption_verify,dict)
            or consumption_verify.get("kind")!="spine_activation_consumption_verify"
            or consumption_verify.get("verified") is not True
            or consumption_verify.get("consumption_digest")!=consumption_digest
            or consumption_verify.get("permit_id")!=permit_id
            or consumption_verify.get("activation_authorized") is not True
            or consumption_verify.get("permit_consumed") is not True
            or consumption_verify.get("runtime_activated") is not False
        ):
            raise SpineRuntimeActivationCommitError("independent activation-consumption verification is required")

        instant=now or datetime.now(timezone.utc)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise SpineRuntimeActivationCommitError("now must be timezone-aware")
        instant=instant.astimezone(timezone.utc)
        commitment_id=hashlib.sha256(f"{consumption_digest}|{permit_id}|pymongo-async".encode("utf-8")).hexdigest()
        evidence={
            "commitment_id":commitment_id,
            "consumption_digest":consumption_digest,
            "permit_id":permit_id,
            "target_driver":"pymongo-async",
            "committed_at":instant.isoformat(),
            "activation_committed":True,
            "runtime_driver_selected":True,
            "runtime_object_replaced":False,
            "dispatcher_started":False,
            "runtime_activated":False,
        }
        payload_digest=_digest(evidence)
        try:
            self._connection.execute(
                """INSERT INTO spine_runtime_activation_commit(
                    commitment_id,consumption_digest,permit_id,target_driver,committed_at,payload_digest
                ) VALUES (?,?,?,?,?,?)""",
                (commitment_id,consumption_digest,permit_id,"pymongo-async",instant.isoformat(),payload_digest),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as exc:
            raise SpineRuntimeActivationCommitError("activation commitment replay refused") from exc
        return {
            "kind":"spine_runtime_activation_commit","hit":False,
            "law":"consumed-activation-permit-commits-intent-not-runtime-activation","citation":"VOL-134",
            **evidence,"digest":payload_digest,"stored_prose":0,"completion_checkbox":False,
            "implementation_signature":False,"verification_signature":False,
        }

    def count(self) -> int:
        return int(self._connection.execute("SELECT COUNT(*) FROM spine_runtime_activation_commit").fetchone()[0])

    def close(self) -> None:
        self._connection.close()
