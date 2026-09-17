"""Pointer dialogue. Predicate gate then verb hint."""

from __future__ import annotations

from typing import Any

from skeleton.game.predicates import eval_named


class DialoguePackError(ValueError):
    pass


NODES: dict[str, tuple[str, str]] = {
    "extract_ready": ("hot", "extract"),
    "need_key": ("has_key", "unlock"),
    "need_sleep": ("can_dream", "dream"),
    "need_scrap": ("has_scrap", "barter"),
    "need_coil": ("coil", "ward"),
    "need_bait": ("bait", "hide"),
    "need_parts": ("has_parts", "craft"),
    "need_calm": ("alert", "calm"),
    "need_path": ("never_extracted", "extract"),
    "need_fog": ("cold", "vent"),
    "need_save": ("extracted_once", "save"),
    "need_quest": ("has_heat", "quest"),
    "need_talk": ("alert", "talk"),
    "need_climb": ("has_heat", "ascend"),
    "need_drop": ("has_heat", "descend"),
    "need_mark": ("threatened", "mark"),
    "need_hide": ("alert", "hide"),
    "need_mend": ("cold", "mend"),
    "need_stoke": ("cold", "stoke"),
    "need_seal": ("can_extract", "seal"),
    "need_doctor": ("has_heat", "doctor"),
    "need_clip": ("has_heat", "clip"),
    "need_warp": ("can_extract", "warp"),
    "need_handoff": ("has_heat", "handoff"),
}


def start(name: str) -> dict[str, Any]:
    if name not in NODES:
        raise DialoguePackError(name)
    pred, verb = NODES[name]
    return {"node": name, "pred": pred, "verb": verb, "open": True, "ok": False, "stored_prose": 0}


def step(card: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    name = str(card.get("node") or "")
    if name not in NODES:
        raise DialoguePackError(name)
    pred, _verb = NODES[name]
    nxt = dict(card)
    try:
        nxt["ok"] = bool(eval_named(state, pred))
    except Exception:
        nxt["ok"] = int(state.get(pred, 0)) >= 1
    nxt["open"] = not nxt["ok"]
    nxt["stored_prose"] = 0
    return nxt
