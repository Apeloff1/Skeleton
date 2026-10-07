"""Replay of an unread probe row.

A matching digest is a duplicate and does not insert. A mismatch fails
closed. Replay does not flip claimed and does not create a missing row.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class SpineProbeReplayError(RuntimeError):
    """Probe replay rejected its inputs. Not a maturity signal."""


class SpineProbeReplay:
    """Re-read one probe row. Do not mint a new one."""

    def __init__(self, journal_path: str | Path, *, table: str) -> None:
        if table not in {"spine_provider_probe", "spine_pr_probe"}:
            raise SpineProbeReplayError("table is not an unread probe journal")
        self._table = table
        self._name = "surface" if table == "spine_provider_probe" else "check_name"
        self._connection = sqlite3.connect(str(journal_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def replay(self, *, tenant_id: str, seq: int, digest: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineProbeReplayError("tenant_id must be non-empty text")
        if not isinstance(seq, int) or seq < 1:
            raise SpineProbeReplayError("seq must be a positive int")
        row = self._connection.execute(
            f"SELECT seq, {self._name} AS name, claimed, digest FROM {self._table} WHERE tenant_id = ? AND seq = ?",
            (tenant_id, seq),
        ).fetchone()
        if row is None:
            raise SpineProbeReplayError("replay does not create a missing row")
        if row["digest"] != digest:
            raise SpineProbeReplayError("replay digest mismatch")
        if int(row["claimed"]) != 0:
            raise SpineProbeReplayError("replay saw a green claim")
        return {
            "kind": "spine_probe_replay",
            "hit": True,
            "law": "replay-does-not-insert",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "seq": seq,
            "name": row["name"],
            "duplicate": True,
            "inserted": False,
            "claimed": 0,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
