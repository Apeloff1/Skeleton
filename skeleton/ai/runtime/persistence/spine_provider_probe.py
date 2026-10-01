"""Unread provider-surface probe journal.

Records a named surface as unread. A claim does not write a green row.
A foreign tenant sees an empty journal. A skipped sequence fails closed.
Does not import Motor and does not start a dispatcher.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any


SURFACES = (
    "mongo-live",
    "motor-bootstrap",
    "runtime-dispatcher",
    "provider-health",
)


class SpineProviderProbeError(RuntimeError):
    """Provider probe rejected its inputs. Not a maturity signal."""


class SpineProviderProbe:
    """Append unread probes. Never mark a surface green."""

    def __init__(self, journal_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(journal_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS spine_provider_probe (
                tenant_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                surface TEXT NOT NULL,
                claimed INTEGER NOT NULL,
                reason TEXT NOT NULL,
                prev_digest TEXT NOT NULL,
                digest TEXT NOT NULL,
                PRIMARY KEY (tenant_id, seq)
            )
            """
        )
        self._connection.commit()

    def probe(self, *, tenant_id: str, surface: str) -> dict[str, Any]:
        self._require_tenant(tenant_id)
        if surface not in SURFACES:
            raise SpineProviderProbeError("surface is not in the unread catalog")
        return self._append(tenant_id=tenant_id, surface=surface, reason="unread")

    def claim(self, *, tenant_id: str, surface: str) -> dict[str, Any]:
        self._require_tenant(tenant_id)
        if surface not in SURFACES:
            raise SpineProviderProbeError("surface is not in the unread catalog")
        card = self._append(tenant_id=tenant_id, surface=surface, reason="claim-refused")
        if card["claimed"] != 0:
            raise SpineProviderProbeError("claim wrote a green row")
        card["green"] = False
        card["law"] = "claim-refused"
        return card

    def read(self, tenant_id: str) -> dict[str, Any]:
        self._require_tenant(tenant_id)
        rows = self._rows(tenant_id)
        return {
            "kind": "spine_provider_probe",
            "hit": False,
            "law": "provider-surface-unclaimed",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "seen": len(rows),
            "claimed": sum(int(row["claimed"]) for row in rows),
            "green": False,
            "surfaces": [row["surface"] for row in rows],
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def verify(self, tenant_id: str) -> dict[str, Any]:
        self._require_tenant(tenant_id)
        rows = self._rows(tenant_id)
        gaps: list[int] = []
        mismatch = False
        prev = "0" * 64
        expected = 1
        for row in rows:
            seq = int(row["seq"])
            while expected < seq:
                gaps.append(expected)
                expected += 1
            digest = self._digest(tenant_id, seq, row["surface"], int(row["claimed"]), row["reason"], prev)
            if digest != row["digest"] or row["prev_digest"] != prev or int(row["claimed"]) != 0:
                mismatch = True
            prev = row["digest"]
            expected = seq + 1
        return {
            "kind": "spine_provider_probe",
            "hit": not gaps and not mismatch,
            "law": "provider-surface-unclaimed",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "gaps": gaps,
            "mismatch": mismatch,
            "green": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()

    def _append(self, *, tenant_id: str, surface: str, reason: str) -> dict[str, Any]:
        rows = self._rows(tenant_id)
        prev = rows[-1]["digest"] if rows else "0" * 64
        seq = (int(rows[-1]["seq"]) + 1) if rows else 1
        digest = self._digest(tenant_id, seq, surface, 0, reason, prev)
        self._connection.execute(
            """
            INSERT INTO spine_provider_probe
                (tenant_id, seq, surface, claimed, reason, prev_digest, digest)
            VALUES (?, ?, ?, 0, ?, ?, ?)
            """,
            (tenant_id, seq, surface, reason, prev, digest),
        )
        self._connection.commit()
        return {
            "kind": "spine_provider_probe",
            "hit": False,
            "law": "provider-surface-unclaimed",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "seq": seq,
            "surface": surface,
            "claimed": 0,
            "reason": reason,
            "green": False,
            "digest": digest,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def _rows(self, tenant_id: str) -> list[sqlite3.Row]:
        return list(
            self._connection.execute(
                """
                SELECT seq, surface, claimed, reason, prev_digest, digest
                FROM spine_provider_probe
                WHERE tenant_id = ?
                ORDER BY seq
                """,
                (tenant_id,),
            )
        )

    def _require_tenant(self, tenant_id: str) -> None:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineProviderProbeError("tenant_id must be non-empty text")

    @staticmethod
    def _digest(tenant_id: str, seq: int, surface: str, claimed: int, reason: str, prev: str) -> str:
        body = f"{tenant_id}|{seq}|{surface}|{claimed}|{reason}|{prev}".encode()
        return hashlib.sha256(body).hexdigest()
