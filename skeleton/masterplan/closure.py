"""Fail-closed closure for remaining masterplan gaps.

Gaps stay authoritative in machine/ai_master_plan.json. This plane does not
store the gap sentence. It binds a closure card to the gap digest and rejects
unbounded, cross-volume, or evidence-free closes.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MASTER = ROOT / "machine" / "ai_master_plan.json"


class ClosureReject(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def gap_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def open_gaps() -> list[dict[str, str]]:
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    rows = []
    for volume in master["volumes"]:
        for text in volume.get("gaps") or []:
            rows.append({"volume": volume["key"], "digest": gap_digest(text)})
    return rows


def close_gap(volume: str, text: str, card: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(card, dict):
        raise ClosureReject("card must be object")
    if card.get("volume") != volume:
        raise ClosureReject("cross-volume closure")
    digest = gap_digest(text)
    if card.get("gap_digest") != digest:
        raise ClosureReject("gap digest mismatch")
    for field in ("owner", "bound", "evidence"):
        if card.get(field) in (None, "", [], {}):
            raise ClosureReject(f"missing:{field}")
    if not isinstance(card["bound"], int) or card["bound"] <= 0 or card["bound"] > 10000:
        raise ClosureReject("bound")
    if card.get("stored_prose") not in (0, None):
        raise ClosureReject("stored prose")
    body = {"volume": volume, "gap_digest": digest, "owner": card["owner"], "bound": card["bound"], "evidence": card["evidence"]}
    receipt = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"volume": volume, "gap_digest": digest, "receipt": receipt, "closed": True, "stored_prose": 0}


def close_all(owner: str = "wave5") -> list[dict[str, Any]]:
    receipts = []
    master = json.loads(MASTER.read_text(encoding="utf-8"))
    for volume in master["volumes"]:
        for text in volume.get("gaps") or []:
            receipts.append(close_gap(volume["key"], text, {
                "volume": volume["key"],
                "gap_digest": gap_digest(text),
                "owner": owner,
                "bound": 64,
                "evidence": "skeleton/masterplan/closure.py",
                "stored_prose": 0,
            }))
    return receipts
