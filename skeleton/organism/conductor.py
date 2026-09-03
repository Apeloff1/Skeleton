"""Editor conductor — 5th brain traffic control.

One verb. Priority is a law, not a vibe:

  1. stored_prose > 0     → doctor
  2. pressure ≥ 0.82      → tighten / switch-tight
  3. cage.denied ≥ 8      → doctor
  4. rot verdict          → dream
  5. coverage < 0.20      → bind-source
  6. no day yet           → day
  7. dumps == 0           → week
  8. else                 → hint() code or pulse

run() executes the verb. decide() is the card.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_LAST: str = ""
_HOLD: int = 0
FOLLOW: Dict[str, Tuple[str, str]] = {
    "doctor": ("pulse", "day"),
    "tighten": ("hold", "pulse"),
    "day": ("pulse", "week"),
    "week": ("pulse", "doctor"),
    "dream": ("pulse", "day"),
    "bind-source": ("pulse", "day"),
    "pulse": ("day", "pulse"),
    "hold": ("pulse", "day"),
}


def decide(org=None, *, neo=None) -> Dict[str, Any]:
    from skeleton.organism.calendar import card as cal_card
    from skeleton.organism.caps import card as caps_card
    from skeleton.organism.laws import scan_prose
    from skeleton.organism.organismer import live_organismer
    from skeleton.social.coverage import coverage_card

    org = org or live_organismer()
    pressure = float(caps_card().get("pressure") or 0)
    prose = 0
    try:
        prose = int(scan_prose(org.galaxy.mesh) or 0)
    except Exception:
        prose = 0
    cage = {}
    try:
        from skeleton.galaxy.quarantine import card as cage_card
        cage = cage_card()
    except Exception:
        cage = {}
    cal = cal_card(getattr(org, "root", None))
    cov = coverage_card("")
    rot = str(cal.get("rot") or "")
    code, why = "pulse", "gap"
    if prose:
        code, why = "doctor", "prose"
    elif pressure >= 0.82:
        code, why = "tighten", "pressure"
    elif int(cage.get("denied") or 0) >= 8:
        code, why = "doctor", "cage"
    elif rot == "rot":
        code, why = "dream", "rot"
    elif float((__import__("skeleton.organism.context_step", fromlist=["last"]).last(getattr(org, "root", None)).get("recall") or 1)) < 0.50:
        code, why = "dream", "recall"
    elif float((__import__("skeleton.organism.observe", fromlist=["card"]).card(getattr(org, "root", None)).get("delta_G") or 0)) < 0 and int((__import__("skeleton.organism.observe", fromlist=["card"]).card(getattr(org, "root", None)).get("n") or 0)) >= 3:
        code, why = "contact", "growth"
    elif float(cov.get("score") or 0) < 0.20:
        code, why = "bind-source", "coverage"
    elif int(cal.get("day_n") or 0) == 0:
        code, why = "day", "no-day"
    elif int(cal.get("dumps") or 0) == 0:
        code, why = "week", "no-dump"
    else:
        try:
            from skeleton.organism.next import hint
            nxt = hint(org, neo=neo)
            code, why = str(nxt.get("code") or "pulse"), str(nxt.get("why") or "hint")
        except Exception:
            code, why = "pulse", "gap"
    code, why, latch = _latch(code, why)
    horizon: List[str] = [code, *FOLLOW.get(code, ("pulse", "day"))]
    out = {
        "kind": "conductor",
        "brain": "editor",
        "code": code,
        "why": why,
        "horizon": horizon,
        "latch": latch,
        "pressure": round(pressure, 4),
        "prose": prose,
        "cage_denied": int(cage.get("denied") or 0),
        "coverage": cov.get("score"),
        "rot": rot,
        "day_n": cal.get("day_n"),
        "dumps": cal.get("dumps"),
        "stored_prose": 0,
    }
    try:
        from skeleton.organism.helix import stamp
        out["helix"] = stamp(org, {
            "code": code,
            "why": why,
            "phase": "conductor",
            "stored_prose": 0,
        }, root=getattr(org, "root", None))
    except Exception:
        out["helix"] = {}
    try:
        _save(out, root=getattr(org, "root", None))
    except Exception:
        pass
    return out


def _latch(code: str, why: str) -> Tuple[str, str, int]:
    global _LAST, _HOLD
    if not _LAST or code == _LAST:
        _LAST = code
        _HOLD += 1
        return code, why, _HOLD
    sticky = _LAST in {"doctor", "tighten"} and why not in {"prose", "pressure"}
    if sticky and _HOLD < 2:
        _HOLD += 1
        return _LAST, "hysteresis", _HOLD
    _LAST = code
    _HOLD = 1
    return code, why, _HOLD


def _act(code: str, org, *, neo=None) -> Dict[str, Any]:
    acted: Dict[str, Any] = {}
    if code == "doctor":
        from skeleton.organism.doctor import doctor_card
        acted = doctor_card(org, neo=neo, fix=True)
    elif code == "tighten":
        from skeleton.kernel.switch import to as switch_to
        acted = switch_to("tight")
    elif code == "day":
        from skeleton.organism.day import run as day_run
        acted = day_run(org, n=1, neo=neo)
    elif code == "week":
        from skeleton.organism.week import run as week_run
        acted = week_run(org, days=1, neo=neo)
    elif code == "bind-source":
        from skeleton.social.seed import seed_field
        acted = seed_field(org.galaxy)
    elif code == "dream":
        from skeleton.organism.sleep import cycle
        acted = cycle(org, neo=neo, force=True)
    else:
        from skeleton.organism.pulse import pulse
        acted = pulse(org, neo=neo, stimulus="")
    return acted


def run(org=None, *, neo=None) -> Dict[str, Any]:
    org = org or __import__("skeleton.organism.organismer", fromlist=["live_organismer"]).live_organismer()
    plan = decide(org, neo=neo)
    acted = _act(plan["code"], org, neo=neo)
    return {
        "kind": "conductor-run",
        "code": plan["code"],
        "why": plan.get("why"),
        "acted": {k: acted.get(k) for k in ("kind", "ok", "n", "head", "profile", "minted") if k in acted},
        "stored_prose": 0,
    }


def commit(org=None, *, neo=None) -> Dict[str, Any]:
    """Run horizon[0] only. Queue the rest. Interrupt on prose/pressure."""
    org = org or __import__("skeleton.organism.organismer", fromlist=["live_organismer"]).live_organismer()
    root = getattr(org, "root", None)
    plan = decide(org, neo=neo)
    rest = _load_rest(root)
    interrupt = plan.get("why") in {"prose", "pressure"}
    if interrupt or not rest:
        code = plan["code"]
        rest = list(plan.get("horizon") or [])[1:]
        source = "law" if interrupt or not rest else "law"
        if interrupt:
            source = "interrupt"
        else:
            source = "fresh"
    else:
        code = rest[0]
        rest = rest[1:]
        source = "horizon"
    acted = _act(code, org, neo=neo)
    _save_rest(rest, root=root)
    return {
        "kind": "conductor-commit",
        "code": code,
        "why": plan.get("why"),
        "source": source,
        "rest": rest,
        "acted": {k: acted.get(k) for k in ("kind", "ok", "n", "head", "profile", "minted") if k in acted},
        "stored_prose": 0,
    }


def _rest_path(root: Optional[Path] = None) -> Path:
    base = Path(root) if root else Path(".")
    return base / "chronicle" / "horizon.json"


def _load_rest(root: Optional[Path] = None) -> List[str]:
    p = _rest_path(root)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return [str(x) for x in (data.get("rest") or []) if x]
    except Exception:
        return []


def _save_rest(rest: List[str], *, root: Optional[Path] = None) -> None:
    p = _rest_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"kind": "horizon", "rest": rest, "stored_prose": 0}, indent=2), encoding="utf-8")


def _save(card: Dict[str, Any], *, root: Optional[Path] = None) -> None:
    base = Path(root) if root else Path(".")
    p = base / "chronicle" / "conductor.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    slim = {k: card.get(k) for k in ("kind", "code", "why", "horizon", "latch", "pressure", "rot", "coverage", "stored_prose")}
    p.write_text(json.dumps(slim, indent=2), encoding="utf-8")
