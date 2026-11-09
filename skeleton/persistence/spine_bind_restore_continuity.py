"""Continuity proof joining a restore receipt to its durable journal evidence."""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineBindRestoreContinuityError(RuntimeError):
    """Restore continuity rejected its inputs. Not a maturity signal."""


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class SpineBindRestoreContinuity:
    """Prove the current receipt remains durable, isolated, and replay-safe."""

    def card(
        self,
        *,
        receipt: dict[str, Any],
        journal: dict[str, Any],
        replay: dict[str, Any],
        tenant: dict[str, Any],
        chain: dict[str, Any],
    ) -> dict[str, Any]:
        expected = {
            "receipt": "spine_bind_restore_receipt",
            "journal": "spine_bind_restore_journal",
            "replay": "spine_bind_restore_replay",
            "tenant": "spine_bind_restore_tenant",
            "chain": "spine_bind_restore_chain",
        }
        cards = {
            "receipt": receipt,
            "journal": journal,
            "replay": replay,
            "tenant": tenant,
            "chain": chain,
        }
        for name, card in cards.items():
            if not isinstance(card, dict) or card.get("kind") != expected[name]:
                raise SpineBindRestoreContinuityError(f"{name} kind mismatch")

        tenant_id = receipt.get("tenant_id")
        receipt_digest = receipt.get("digest")
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindRestoreContinuityError("receipt tenant missing")
        if not isinstance(receipt_digest, str) or len(receipt_digest) != 64:
            raise SpineBindRestoreContinuityError("receipt digest missing")
        for name, card in cards.items():
            if card.get("tenant_id") != tenant_id:
                raise SpineBindRestoreContinuityError(f"{name} tenant mismatch")
            if card.get("activated") is not False:
                raise SpineBindRestoreContinuityError(f"{name} activated")

        if journal.get("receipt_digest") != receipt_digest:
            raise SpineBindRestoreContinuityError("journal receipt digest mismatch")
        if replay.get("receipt_digest") != receipt_digest:
            raise SpineBindRestoreContinuityError("replay receipt digest mismatch")
        if replay.get("row_digest") != journal.get("row_digest"):
            raise SpineBindRestoreContinuityError("replay row digest mismatch")
        if replay.get("inserted") is not False or replay.get("rewritten") is not False:
            raise SpineBindRestoreContinuityError("replay mutated restore journal")
        if replay.get("rows_before") != replay.get("rows_after"):
            raise SpineBindRestoreContinuityError("replay row count changed")
        if tenant.get("foreign") != 0:
            raise SpineBindRestoreContinuityError("foreign restore receipt visible")
        if receipt_digest not in tenant.get("receipt_digests", []):
            raise SpineBindRestoreContinuityError("tenant view lost restore receipt")
        count = tenant.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise SpineBindRestoreContinuityError("tenant restore count invalid")
        if chain.get("rows") != count:
            raise SpineBindRestoreContinuityError("restore chain row count mismatch")
        if chain.get("head_receipt_digest") != receipt_digest:
            raise SpineBindRestoreContinuityError("restore chain head mismatch")
        if chain.get("rewritten") is not False:
            raise SpineBindRestoreContinuityError("restore chain rewritten")

        body = {
            "kind": "spine_bind_restore_continuity",
            "hit": True,
            "law": "restore-continuity-does-not-activate",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "receipt_digest": receipt_digest,
            "journal_row_digest": journal.get("row_digest"),
            "chain_digest": chain.get("digest"),
            "rows": count,
            "durable": True,
            "tenant_isolated": True,
            "replay_safe": True,
            "activated": False,
            "apply_landed": False,
            "live_motor": False,
            "dispatcher_running": False,
            "provider_surface_green": False,
            "pr_automation_green": False,
            "ci_green": False,
            "merged": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
        body["digest"] = _digest(body)
        return body
