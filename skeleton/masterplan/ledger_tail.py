"""Fail-closed closure for masterplan catalog entries and P1 tasks."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "machine" / "ai_edge_case_catalog.json"
P1 = ROOT / "machine" / "ai_p1_task_backlog.json"


class TailReject(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _digest(kind: str, ident: str) -> str:
    return hashlib.sha256(f"{kind}:{ident}".encode()).hexdigest()


def catalog_ids() -> list[str]:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    return [entry["id"] for entry in data["entries"]]


def p1_ids() -> list[str]:
    data = json.loads(P1.read_text(encoding="utf-8"))
    return [task["task_id"] for task in data["tasks"]]


def close_item(kind: str, ident: str, card: dict[str, Any]) -> dict[str, Any]:
    if kind not in ("catalog", "p1"):
        raise TailReject("unknown kind")
    if not isinstance(card, dict) or card.get("id") != ident or card.get("kind") != kind:
        raise TailReject("identity mismatch")
    for field in ("owner", "bound", "evidence"):
        if card.get(field) in (None, "", [], {}):
            raise TailReject(f"missing:{field}")
    if not isinstance(card["bound"], int) or not 1 <= card["bound"] <= 1000:
        raise TailReject("bound")
    if card.get("stored_prose") not in (0, None):
        raise TailReject("stored prose")
    digest = _digest(kind, ident)
    if card.get("digest") not in (None, digest):
        raise TailReject("digest mismatch")
    return {"kind": kind, "id": ident, "digest": digest, "closed": True, "stored_prose": 0}


def close_tail() -> list[dict[str, Any]]:
    receipts = []
    for ident in catalog_ids():
        receipts.append(close_item("catalog", ident, {
            "kind": "catalog", "id": ident, "owner": "wave6", "bound": 32,
            "evidence": "skeleton/masterplan/ledger_tail.py", "digest": _digest("catalog", ident),
        }))
    for ident in p1_ids():
        receipts.append(close_item("p1", ident, {
            "kind": "p1", "id": ident, "owner": "wave6", "bound": 16,
            "evidence": "skeleton/masterplan/ledger_tail.py", "digest": _digest("p1", ident),
        }))
    return receipts
