"""Flake lifecycle cards. Not the #1030 quality harness."""

from __future__ import annotations

from typing import Any


STATES = ("open", "quarantine", "expired", "closed")
MAX_FLAKES = 32


class FlakeError(ValueError):
    """Flake lifecycle contract violation."""


def open_flake(*, test_id: str, digest: str) -> dict[str, Any]:
    name = str(test_id or "").strip()
    seal = str(digest or "").strip()
    if not name or len(name) > 80:
        raise FlakeError("test_id invalid")
    if len(seal) != 64 or any(ch not in "0123456789abcdef" for ch in seal):
        raise FlakeError("digest must be sha256 hex")
    return {
        "kind": "flake",
        "test_id": name,
        "digest": seal,
        "state": "open",
        "stored_prose": 0,
    }


def advance(card: dict[str, Any], action: str) -> dict[str, Any]:
    state = str((card or {}).get("state") or "")
    move = str(action or "").strip().lower()
    table = {
        ("open", "quarantine"): "quarantine",
        ("quarantine", "expire"): "expired",
        ("quarantine", "close"): "closed",
        ("open", "close"): "closed",
        ("expired", "close"): "closed",
    }
    nxt = table.get((state, move))
    if nxt is None:
        raise FlakeError(f"illegal transition {state}->{move}")
    out = dict(card)
    out["state"] = nxt
    out["stored_prose"] = 0
    return out


def ledger(cards: list[dict[str, Any]] | None) -> dict[str, Any]:
    rows = list(cards or [])
    if len(rows) > MAX_FLAKES:
        raise FlakeError("too many flakes")
    return {
        "kind": "flake_ledger",
        "n": len(rows),
        "open": sum(1 for row in rows if row.get("state") == "open"),
        "cards": rows,
        "stored_prose": 0,
    }
