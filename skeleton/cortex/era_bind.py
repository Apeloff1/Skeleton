"""Era bind — titles, slogans and house ids collapse onto one pack.

Refs speak ``cozy``. The forge compiles ``cozy_wholesome``. A vision
``like Elden Ring`` is neither string. This module is the perpendicular
cut that makes those three planes name the same dialect.

Laws: pointer + house dialect only. No Steam/Wiki prose.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from skeleton.cortex.laws import check
from skeleton.cortex.refs import lookup, refer

# ref-era (acquire_repo.SPREE) → forge ERA_IDS
HOUSE_ERA: Dict[str, str] = {
    "soulslike": "soulslike",
    "roguelike": "roguelike",
    "metroidvania": "metroidvania",
    "extraction_now": "extraction_now",
    "extraction": "extraction_now",
    "cozy": "cozy_wholesome",
    "cozy_wholesome": "cozy_wholesome",
    "horror": "horror_survival",
    "horror_survival": "horror_survival",
    "boomer": "boomer_shooter",
    "boomer_shooter": "boomer_shooter",
    "stealth": "stealth",
    "tactics": "tactics_grid",
    "tactics_grid": "tactics_grid",
    "jrpg": "jrpg",
    "crpg": "crpg",
    "immersive_sim": "immersive_sim",
    "deckbuilder": "deckbuilder",
    "bullet_heaven": "bullet_heaven",
    "battle_royale": "battle_royale",
    "mmorpg": "mmorpg",
    "visual_novel": "visual_novel",
    "walking_sim": "walking_sim",
    "grand_strategy": "grand_strategy",
    "city_builder": "city_builder",
    "indie": "indie_experimental",
    "indie_experimental": "indie_experimental",
    "modern_aaa": "modern_aaa",
    "arcade": "arcade_golden_age",
    "arcade_golden_age": "arcade_golden_age",
    "fighting": "fighting_game",
    "fighting_game": "fighting_game",
}

_LIKE = re.compile(r"\blike\s+(.+)$", re.I)
_TOKEN = re.compile(r"[a-z0-9]+")


def house_era(name: str) -> str:
    key = " ".join((name or "").lower().replace("-", "_").split())
    key = key.replace(" ", "_")
    if key in HOUSE_ERA:
        return HOUSE_ERA[key]
    compact = key.replace("_", "")
    for alias, era in HOUSE_ERA.items():
        if alias.replace("_", "") == compact:
            return era
    return "extraction_now"


def _tokens(s: str) -> Tuple[str, ...]:
    return tuple(_TOKEN.findall((s or "").lower()))


def resolve(stimulus: str, *, live: bool = False) -> Dict[str, Any]:
    """Vision / title / era-id → house era + citation + dialect. Never prose."""
    stim = stimulus or ""
    hit = refer(stim, live=live) if stim else {"hit": 0}
    ref: Optional[Dict[str, Any]] = hit.get("ref") if hit.get("hit") else None
    if ref is None:
        m = _LIKE.search(stim)
        if m:
            hit = refer(m.group(1), live=live)
            ref = hit.get("ref") if hit.get("hit") else None
    if ref is None:
        ref = lookup(stim)
        if ref is not None:
            hit = {"hit": 1, "ref": ref, "live": 0}

    raw_era = ""
    if ref is not None:
        raw_era = str(ref.get("era") or "")
    if not raw_era:
        raw_era = stim
    era = house_era(raw_era)
    if era == "extraction_now" and ref is None:
        # last chance: any house alias token in the vision
        for tok in _tokens(stim):
            mapped = house_era(tok)
            if mapped != "extraction_now" or tok in {"extraction", "extract"}:
                era = mapped
                break

    from skeleton.forge.eras import compile_era

    pack = compile_era(era)
    card = check({
        "kind": "era-bind",
        "stimulus": stim[:160],
        "era": era,
        "ref_era": (ref or {}).get("era"),
        "title": (ref or {}).get("title"),
        "appid": (ref or {}).get("appid"),
        "url": (ref or {}).get("url"),
        "citation": (ref or {}).get("citation"),
        "dialect": (ref or {}).get("dialect") or pack.get("era"),
        "primary_dps": pack.get("primary_dps"),
        "room_bias": pack.get("room_bias") or pack.get("meta", {}).get("philosophy"),
        "philosophy": (pack.get("meta") or {}).get("philosophy"),
        "ttk": dict(pack.get("ttk") or {}),
        "hit": int(bool(ref)),
        "stored_prose": 0,
        "law": "ok",
        "pack_era": pack.get("era"),
    })
    card["pack"] = pack
    return card


def bind_into(jeeves, stimulus: str) -> Dict[str, Any]:
    """Resolve then bind_pack on a live Jeeves. Returns the card, not the pack."""
    card = resolve(stimulus)
    pack = card.get("pack") or {}
    if hasattr(jeeves, "bind_pack"):
        bound = jeeves.bind_pack(pack)
        card["bound_era"] = bound.get("era")
        card["bound_dps"] = bound.get("primary_dps")
    return card
