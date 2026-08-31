"""Doctor — laws, health, caps, field, next in one fail-closed card."""
from __future__ import annotations

from typing import Any, Dict


def _version() -> str:
    from skeleton.organism.product import VERSION
    return VERSION


def doctor_card(org=None, *, neo=None) -> Dict[str, Any]:
    from skeleton.organism.caps import card as caps_card
    from skeleton.organism.health import health_card
    from skeleton.organism.next import hint
    from skeleton.organism.organismer import live_organismer
    from skeleton.social.field import field_card

    org = org or live_organismer()
    health = health_card(org, neo=neo)
    caps = caps_card()
    field = field_card()
    nxt = hint(org, neo=neo)
    prose = int(health.get("stored_prose") or 0)
    ok = int(bool(health.get("ok")) and prose == 0 and field["n"] >= 16)
    return {
        "kind": "doctor",
        "ok": ok,
        "health_ok": health.get("ok"),
        "stored_prose": prose,
        "pressure": caps.get("pressure"),
        "tier": caps.get("tier"),
        "budget": nxt.get("budget"),
        "next": nxt.get("code"),
        "field_n": field["n"],
        "houses": field["houses"],
        "G": health.get("G"),
        "version": _version(),
        "laws": ("cite-do-not-copy", "stored_prose=0", "clipped-G", "headroom-below-wall"),
    }
