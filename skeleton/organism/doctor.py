"""Doctor — laws, health, caps, field, next in one fail-closed card."""
from __future__ import annotations

from typing import Any, Dict


def _version() -> str:
    from skeleton.organism.product import VERSION
    return VERSION


def doctor_card(org=None, *, neo=None, fix: bool = False) -> Dict[str, Any]:
    from skeleton.organism.caps import card as caps_card
    from skeleton.organism.health import health_card
    from skeleton.organism.laws import clip_fat, laws_card, persist_clip
    from skeleton.organism.next import hint
    from skeleton.organism.organismer import live_organismer
    from skeleton.social.field import field_card

    org = org or live_organismer()
    clipped = None
    if fix:
        clipped = clip_fat(org.galaxy.mesh)
        clipped.update(persist_clip(org))
    health = health_card(org, neo=neo)
    caps = caps_card()
    field = field_card()
    nxt = hint(org, neo=neo)
    laws = laws_card(org.galaxy.mesh)
    prose = int(laws.get("stored_prose") or 0)
    helix = {}
    try:
        from skeleton.organism.helix import verify as helix_verify
        helix = helix_verify(getattr(org, "root", None))
    except Exception:
        helix = {"ok": 1, "sense": {"n": 0}, "snap": {"n": 0}}
    verified = {}
    try:
        from skeleton.intelligence.verification import VerificationLoop, VerificationVerdict
        def _v(claim, ctx):
            p = int((ctx or {}).get("prose") or 0)
            return VerificationVerdict(confidence=1.0 if p == 0 else 0.2,
                                      issues=() if p == 0 else ("stored_prose",))
        _, verified_tr = VerificationLoop(max_rounds=2, min_rounds=1).run(
            "stored_prose=0", _v, context={"prose": prose})
        verified = verified_tr.to_dict()
    except Exception:
        verified = {}
    helix_ok = int(helix.get("ok", 1))
    ok = int(bool(health.get("ok")) and prose == 0 and field["n"] >= 16 and helix_ok)
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
        "laws": laws["names"],
        "laws_ok": laws["ok"],
        "fix": clipped,
        "helix_ok": helix_ok,
        "helix_sense_n": (helix.get("sense") or {}).get("n"),
        "helix_snap_n": (helix.get("snap") or {}).get("n"),
        "verified": verified,
        "satellites": __import__("skeleton.organism.satellites", fromlist=["satellites_card"]).satellites_card(org),
    }
