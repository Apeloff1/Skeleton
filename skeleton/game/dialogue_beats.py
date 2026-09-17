"""Wave-4 dialogue beats."""

from __future__ import annotations

from typing import Any


class DialogueBeatError(ValueError):
    pass


BEATS: dict[str, str] = {
    f"beat_{i:02d}": ("hot", "has_heat", "never_extracted", "has_scrap", "alert", "can_dream")[i % 6]
    for i in range(24)
}


def start(name: str) -> dict[str, Any]:
    if name not in BEATS:
        raise DialogueBeatError(name)
    return {"beat": name, "pred": BEATS[name], "ok": False, "stored_prose": 0}


def step(card: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    name = str(card.get("beat") or "")
    if name not in BEATS:
        raise DialogueBeatError(name)
    nxt = dict(card)
    pred = BEATS[name]
    nxt["ok"] = int(state.get(pred, 0)) >= 1
    nxt["stored_prose"] = 0
    return nxt
