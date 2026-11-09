"""Witness for unread PR Automation checks.

Reads the probe journal. A complete catalog still leaves CI green false.
A foreign tenant is empty. Does not query GitHub.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from skeleton.persistence.spine_pr_probe import CHECKS


class SpineCiWitnessError(RuntimeError):
    """CI witness rejected its inputs. Not a maturity signal."""


class SpineCiWitness:
    """Report unread checks. Never mark CI green."""

    def __init__(self, journal_path: str | Path) -> None:
        self._connection = sqlite3.connect(str(journal_path), check_same_thread=False)
        self._connection.row_factory = sqlite3.Row

    def card(self, tenant_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineCiWitnessError("tenant_id must be non-empty text")
        rows = list(
            self._connection.execute(
                """
                SELECT check_name, claimed
                FROM spine_pr_probe
                WHERE tenant_id = ?
                ORDER BY seq
                """,
                (tenant_id,),
            )
        )
        seen = [row["check_name"] for row in rows]
        missing = [name for name in CHECKS if name not in seen]
        claimed = sum(int(row["claimed"]) for row in rows)
        if claimed != 0:
            raise SpineCiWitnessError("probe journal holds a green claim")
        return {
            "kind": "spine_ci_witness",
            "hit": False,
            "law": "ci-green-unread",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "seen": seen,
            "missing": missing,
            "catalog_complete": len(missing) == 0 and len(seen) > 0,
            "ci_green": False,
            "claimed": 0,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
