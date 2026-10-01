"""Hash chain over independently reconstructable bind-hold refusal rows."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path
from typing import Any

from skeleton.persistence.spine_bind_hold_journal import (
    _bind_hold_refusal_digest,
)


class SpineBindHoldChainError(RuntimeError):
    """Bind hold chain rejected its inputs. Not a maturity signal."""


_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


class SpineBindHoldChain:
    """Seal durable refusal rows into a SHA-256 chain."""

    def __init__(self, journal_path: str | Path) -> None:
        self._connection = sqlite3.connect(
            str(journal_path),
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row

    def seal(self, tenant_id: str) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindHoldChainError("tenant_id must be non-empty text")
        try:
            rows = self._connection.execute(
                """
                SELECT refusal_id, tenant_id, outbox_id, hold_id, hold_reason,
                       bind_digest, digest, held, applied, epoch
                FROM spine_bind_hold
                WHERE tenant_id = ?
                ORDER BY refusal_id
                """,
                (tenant_id,),
            ).fetchall()
        except sqlite3.OperationalError as exc:
            raise SpineBindHoldChainError("bind hold journal missing") from exc

        digest = "0" * 64
        for row in rows:
            refusal_id = int(row["refusal_id"])
            hold_id = int(row["hold_id"])
            hold_reason = str(row["hold_reason"])
            bind_digest = str(row["bind_digest"])
            refusal_digest = str(row["digest"])
            held = int(row["held"])
            applied = int(row["applied"])
            epoch = int(row["epoch"])
            if (
                refusal_id < 1
                or hold_id < 1
                or not hold_reason.strip()
                or _DIGEST_RE.fullmatch(bind_digest) is None
                or _DIGEST_RE.fullmatch(refusal_digest) is None
                or held != 1
                or applied != 0
                or epoch < 0
            ):
                raise SpineBindHoldChainError("refusal row is not dark")
            expected = _bind_hold_refusal_digest(
                tenant_id=str(row["tenant_id"]),
                outbox_id=str(row["outbox_id"]),
                hold_id=hold_id,
                hold_reason=hold_reason,
                bind_digest=bind_digest,
                epoch=epoch,
            )
            if refusal_digest != expected:
                raise SpineBindHoldChainError(
                    "refusal row digest does not match durable evidence"
                )
            payload = "|".join(
                (
                    str(refusal_id),
                    str(row["tenant_id"]),
                    str(row["outbox_id"]),
                    str(hold_id),
                    hold_reason,
                    bind_digest,
                    refusal_digest,
                    str(held),
                    str(applied),
                    str(epoch),
                )
            )
            digest = hashlib.sha256(
                f"{digest}|{payload}".encode("utf-8")
            ).hexdigest()

        return {
            "kind": "spine_bind_hold_chain",
            "hit": True,
            "law": "bind-hold-hash-chain",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "rows": len(rows),
            "digest": digest,
            "applied": 0,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def verify(self, tenant_id: str, expected_digest: str) -> dict[str, Any]:
        if (
            not isinstance(expected_digest, str)
            or _DIGEST_RE.fullmatch(expected_digest) is None
        ):
            raise SpineBindHoldChainError(
                "expected digest must be lowercase SHA-256 hex"
            )
        card = self.seal(tenant_id)
        return {
            "kind": "spine_bind_hold_chain_verify",
            "hit": True,
            "law": "bind-hold-chain-verification-does-not-apply",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "rows": card["rows"],
            "digest": card["digest"],
            "expected_digest": expected_digest,
            "match": card["digest"] == expected_digest,
            "applied": 0,
            "apply_authority": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }

    def close(self) -> None:
        self._connection.close()
