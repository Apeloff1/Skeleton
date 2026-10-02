"""Deterministic snapshot of the dark bind/recovery evidence surface.

The snapshot joins already-produced cards. It never starts a dispatcher,
imports Motor, fills a sequence gap, claims an external surface, or advances a
consistency fence.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


class SpineBindSnapshotError(RuntimeError):
    """Bind snapshot rejected its inputs. Not a maturity signal."""


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class SpineBindSnapshot:
    """Seal bind evidence into one deterministic, still-dark snapshot."""

    def card(
        self,
        *,
        tenant_id: str,
        bind: dict[str, Any],
        chain: dict[str, Any],
        gap: dict[str, Any],
        surface: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise SpineBindSnapshotError("tenant_id must be non-empty text")
        self._require_bind(tenant_id, bind)
        self._require_chain(tenant_id, chain)
        self._require_gap(tenant_id, gap)
        self._require_surface(tenant_id, surface)

        body = {
            "kind": "spine_bind_snapshot",
            "hit": False,
            "law": "bind-snapshot-stays-unactivated",
            "citation": "VOL-134",
            "tenant_id": tenant_id,
            "bind_digest": bind["digest"],
            "chain_digest": chain["digest"],
            "missing": list(gap["missing"]),
            "provider_claimed": False,
            "pr_claimed": False,
            "gap_filled": False,
            "live_motor": False,
            "dispatcher_running": False,
            "ci_green": False,
            "merged": False,
            "apply_landed": False,
            "activated": False,
            "stored_prose": 0,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
        body["digest"] = _digest(body)
        return body

    @staticmethod
    def _require_bind(tenant_id: str, card: dict[str, Any]) -> None:
        if not isinstance(card, dict) or card.get("kind") != "spine_bind_card":
            raise SpineBindSnapshotError("bind must be a spine_bind_card")
        if card.get("tenant_id") != tenant_id:
            raise SpineBindSnapshotError("bind tenant does not match")
        if card.get("moved") is not False or card.get("apply_landed") is not False:
            raise SpineBindSnapshotError("bind card is not dark")
        digest = card.get("digest")
        if not isinstance(digest, str) or len(digest) != 64:
            raise SpineBindSnapshotError("bind digest missing")

    @staticmethod
    def _require_chain(tenant_id: str, card: dict[str, Any]) -> None:
        if not isinstance(card, dict) or card.get("kind") != "spine_bind_chain":
            raise SpineBindSnapshotError("chain must be a spine_bind_chain")
        if card.get("tenant_id") != tenant_id:
            raise SpineBindSnapshotError("chain tenant does not match")
        if card.get("rewritten") is not False or card.get("merged") is not False:
            raise SpineBindSnapshotError("bind chain is not dark")
        digest = card.get("digest")
        if not isinstance(digest, str) or len(digest) != 64:
            raise SpineBindSnapshotError("chain digest missing")

    @staticmethod
    def _require_gap(tenant_id: str, card: dict[str, Any]) -> None:
        if not isinstance(card, dict) or card.get("kind") != "spine_bind_gap":
            raise SpineBindSnapshotError("gap must be a spine_bind_gap")
        if card.get("tenant_id") != tenant_id:
            raise SpineBindSnapshotError("gap tenant does not match")
        if card.get("filled") is not False or card.get("green") is not False:
            raise SpineBindSnapshotError("bind gap was filled or promoted")
        missing = card.get("missing")
        if not isinstance(missing, list):
            raise SpineBindSnapshotError("gap missing list absent")

    @staticmethod
    def _require_surface(tenant_id: str, card: dict[str, Any]) -> None:
        if not isinstance(card, dict) or card.get("kind") != "spine_bind_surface":
            raise SpineBindSnapshotError("surface must be a spine_bind_surface")
        if card.get("tenant_id") != tenant_id:
            raise SpineBindSnapshotError("surface tenant does not match")
        for flag in ("provider_claimed", "pr_claimed"):
            if card.get(flag) not in (0, False):
                raise SpineBindSnapshotError("bind surface is claimed")
        for flag in ("green", "merged"):
            if card.get(flag) is not False:
                raise SpineBindSnapshotError("bind surface is not unread")
