"""Perpendicular cut — seven axes fire as one instrument.

A linear "keep going" walk only thickens the last file. A perpendicular
cut walks the organism sideways:

    REF     pointer lookup (cite, never copy)
    ERA     house-era bind (title ≠ forge id)
    LAW     check() on the amalgam
    TEACH   contact every HuggingFace / Kimi mouth
    ASCEND  "like <title>" raises house weights
    GENOS   one G pulse, mag-capped
    OBSERVE card: G + law + citation + stored_prose=0

Each axis is independently fail-closed. The card is the merkle of the
cut, not a transcript of third-party pages.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List

from skeleton.cortex.contact import is_teacher
from skeleton.cortex.era_bind import resolve
from skeleton.cortex.laws import LawError, check
from skeleton.cortex.refs import refer


AXES = ("ref", "era", "law", "teach", "ascend", "genos", "observe")


def _g(neo) -> float:
    return float(getattr(getattr(neo, "genos_engine", None), "G", 1.0) or 1.0)


def _contact_teachers(neo, stimulus: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    slots = getattr(neo, "slots", {}) or {}
    touch = getattr(neo, "contact", None)
    for slot, port in slots.items():
        if not is_teacher(port):
            continue
        if callable(touch):
            card = touch(slot, stimulus)
        else:
            card = {"contacted": 0, "reason": "no-contact", "slot": slot}
        out.append(card if isinstance(card, dict) else {"slot": slot})
    return out


def cut(neo, stimulus: str, *, rounds: int = 3, live: bool = False) -> Dict[str, Any]:
    """Run the seven-axis cut. Laws gate the returned card."""
    stim = stimulus or ""
    axes: Dict[str, Any] = {k: {"ok": 0} for k in AXES}

    # REF
    ref_hit = refer(stim, live=live)
    axes["ref"] = {
        "ok": int(bool(ref_hit.get("hit"))),
        "title": (ref_hit.get("ref") or {}).get("title"),
        "citation": (ref_hit.get("ref") or {}).get("citation"),
        "url": (ref_hit.get("ref") or {}).get("url"),
        "stored_prose": 0,
    }

    # ERA
    bound = resolve(stim, live=live)
    axes["era"] = {
        "ok": 1,
        "era": bound.get("era"),
        "pack_era": bound.get("pack_era"),
        "primary_dps": bound.get("primary_dps"),
        "philosophy": bound.get("philosophy"),
        "hit": bound.get("hit"),
    }
    if hasattr(neo, "bind_pack") and bound.get("pack"):
        try:
            neo.bind_pack(bound["pack"])
            axes["era"]["bound"] = 1
        except Exception as exc:
            axes["era"]["bound"] = 0
            axes["era"]["error"] = type(exc).__name__

    # LAW
    try:
        check({
            "kind": "perpendicular",
            "dialect": str(bound.get("dialect") or "")[:160],
            "title": bound.get("title") or "",
            "era": bound.get("era"),
            "stored_prose": 0,
        })
        axes["law"] = {"ok": 1, "law": "ok"}
    except LawError as exc:
        axes["law"] = {"ok": 0, "law": exc.law, "detail": str(exc)}

    # TEACH
    contacts = _contact_teachers(neo, stim)
    axes["teach"] = {
        "ok": int(any(c.get("contacted") for c in contacts)) if contacts else 0,
        "n": len(contacts),
        "contacts": contacts,
        "magnitude": max((float(c.get("magnitude") or 1.0) for c in contacts), default=1.0),
    }

    # ASCEND
    improve_card: Dict[str, Any] = {"improved": 0}
    like = "like " in stim.lower()
    if like and (ref_hit.get("hit") or bound.get("hit")):
        if hasattr(neo, "ascend"):
            improve_card = neo.ascend(stim, rounds=max(2, int(rounds)))
        elif hasattr(neo, "improve"):
            improve_card = neo.improve(stim, rounds=max(2, int(rounds)))
        else:
            from skeleton.cortex.improve import improve as improve_fn
            improve_card = improve_fn(neo, stim, rounds=max(2, int(rounds)))
    axes["ascend"] = {
        "ok": int(bool(improve_card.get("improved"))),
        "kind": improve_card.get("kind") or "idle",
        "ratio": improve_card.get("ratio"),
        "G": improve_card.get("G"),
    }

    # GENOS — one pulse. Magnitude already capped inside Genos.
    genos_card: Dict[str, Any] = {"ok": 0}
    if hasattr(neo, "genos"):
        genos_card = neo.genos(stim or "plan tensor ttk lattice soulslike")
    else:
        engine = getattr(neo, "genos_engine", None)
        if engine is not None and hasattr(engine, "pulse"):
            genos_card = engine.pulse(neo, stimulus=stim or "plan tensor ttk lattice soulslike")
    axes["genos"] = {
        "ok": int(bool(genos_card.get("ok"))),
        "G": genos_card.get("G") or round(_g(neo), 6),
        "pulse": genos_card.get("pulse") or genos_card.get("pulses"),
        "M": genos_card.get("M"),
        "epsilon": genos_card.get("epsilon"),
    }

    # OBSERVE
    g = _g(neo)
    toward = min(100.0, max(0.0, (g - 1.0) / 9.0 * 100.0))
    axes["observe"] = {
        "ok": 1,
        "G": round(g, 6),
        "target": 10.0,
        "toward_pct": round(toward, 1),
        "citation": axes["ref"].get("citation") or bound.get("citation"),
        "stored_prose": 0,
        "law": axes["law"].get("law") or "ok",
        "era": bound.get("era"),
    }

    card = check({
        "kind": "perpendicular",
        "stimulus": stim[:240],
        "axes": {k: {kk: vv for kk, vv in v.items() if kk != "contacts"} for k, v in axes.items()},
        "teachers": contacts,
        "era": bound.get("era"),
        "title": bound.get("title") or axes["ref"].get("title"),
        "citation": axes["observe"]["citation"],
        "url": axes["ref"].get("url") or bound.get("url"),
        "G": round(g, 6),
        "target": 10.0,
        "toward_pct": round(toward, 1),
        "law": axes["law"].get("law") or "ok",
        "stored_prose": 0,
        "hit": int(bool(bound.get("hit") or ref_hit.get("hit"))),
        "improved": int(bool(improve_card.get("improved"))),
        "contacts": len(contacts),
        "at": int(time.time() * 1000),
    })
    # contacts restored after check — they are house cards, not prose
    card["axes"]["teach"]["contacts"] = contacts
    card["improve"] = {k: improve_card.get(k) for k in
                       ("improved", "kind", "title", "era", "G0", "G", "ratio", "citation", "stored_prose")
                       if k in improve_card}
    card["genos"] = {k: genos_card.get(k) for k in
                     ("ok", "G", "pulse", "M", "H", "C", "epsilon", "growth")
                     if k in genos_card}
    card["pack_era"] = bound.get("pack_era")
    card["primary_dps"] = bound.get("primary_dps")
    return card


def live_cut(stimulus: str, **kw) -> Dict[str, Any]:
    from skeleton.cortex.live import live_cortex
    return cut(live_cortex(), stimulus, **kw)
