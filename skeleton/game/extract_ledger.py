"""Extract ledger. Once-only warp. Fail-closed second extract."""

from __future__ import annotations

from typing import Any

from skeleton.game.predicates import require_never_extracted
from skeleton.game.seal_card import seal


class ExtractLedgerError(ValueError):
    pass


def blank(seed: int) -> dict[str, Any]:
    return {
        "seed": int(seed),
        "extracted": 0,
        "warp_count": 0,
        "heat": 0,
        "attempts": 0,
        "denied": 0,
        "stored_prose": 0,
    }


def stoke(card: dict[str, Any], n: int = 1) -> dict[str, Any]:
    nxt = dict(card)
    nxt["heat"] = min(16, int(nxt.get("heat", 0)) + int(n))
    return nxt


def extract(card: dict[str, Any]) -> dict[str, Any]:
    nxt = dict(card)
    nxt["attempts"] = int(nxt.get("attempts", 0)) + 1
    if int(nxt.get("heat", 0)) < 8:
        nxt["denied"] = int(nxt.get("denied", 0)) + 1
        raise ExtractLedgerError("cold")
    try:
        require_never_extracted(nxt)
    except Exception as exc:
        nxt["denied"] = int(nxt.get("denied", 0)) + 1
        raise ExtractLedgerError("twice") from exc
    nxt["extracted"] = 1
    nxt["warp_count"] = 1
    nxt["stored_prose"] = 0
    return nxt


def play(*, seed: int = 8847291) -> dict[str, Any]:
    card = blank(int(seed))
    for _ in range(8):
        card = stoke(card, 1)
    card = extract(card)
    denied = 0
    try:
        extract(card)
    except ExtractLedgerError:
        denied = 1
    return seal({
        "kind": "extract_ledger",
        "seed": int(seed),
        "extract_count": card["extracted"],
        "warp_count": card["warp_count"],
        "denied": denied,
        "attempts": card["attempts"],
        "sota_ready": False,
        "stored_prose": 0,
    })
