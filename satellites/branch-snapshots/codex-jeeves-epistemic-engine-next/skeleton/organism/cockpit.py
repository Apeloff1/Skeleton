"""Cockpit knobs — mutate pack numbers and re-score the walk."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


DEFAULT = {
    "kind": "cockpit",
    "speed_mul": 1.0,
    "heat_mul": 1.0,
    "collapse_mul": 1.0,
    "stored_prose": 0,
}


def path(root: Optional[Path] = None) -> Path:
    base = Path(root) if root else Path(".")
    return base / "game" / "data" / "cockpit.json"


def load(root: Optional[Path] = None) -> Dict[str, Any]:
    p = path(root)
    row = dict(DEFAULT)
    if p.is_file():
        try:
            got = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(got, dict):
                row.update(got)
        except Exception:
            pass
    row["kind"] = "cockpit"
    row["stored_prose"] = 0
    return row


def save(row: Dict[str, Any], root: Optional[Path] = None) -> Path:
    p = path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    out = dict(DEFAULT)
    out.update(row)
    out["kind"] = "cockpit"
    out["stored_prose"] = 0
    p.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return p


def apply(pack: Dict[str, Any], knobs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    k = knobs or DEFAULT
    out = dict(pack)
    player = dict(out.get("player") or {})
    heat = dict(out.get("heat") or {})
    session = dict(out.get("session") or {})
    sm = max(0.5, min(2.0, float(k.get("speed_mul") or 1)))
    hm = max(0.5, min(2.0, float(k.get("heat_mul") or 1)))
    cm = max(0.5, min(2.0, float(k.get("collapse_mul") or 1)))
    player["speed"] = float(player.get("speed") or 180) * sm
    for key in ("passive_cool", "kinetic_heat", "energy_heat", "sprint_heat_per_sec", "max_heat"):
        if key in heat:
            heat[key] = float(heat[key]) * hm
    session["collapse_max"] = float(session.get("collapse_max") or 300) * cm
    out["player"] = player
    out["heat"] = heat
    out["session"] = session
    return out


def retune(pack: Dict[str, Any], graph: Dict[str, Any], *, root: Optional[Path] = None,
           speed_mul: Optional[float] = None) -> Dict[str, Any]:
    from skeleton.forge.walk import walk_graph
    knobs = load(root)
    if speed_mul is not None:
        knobs["speed_mul"] = float(speed_mul)
    save(knobs, root)
    tuned = apply(pack, knobs)
    before = walk_graph(pack, graph).to_dict()
    after = walk_graph(tuned, graph).to_dict()
    return {
        "kind": "cockpit-retune",
        "knobs": {k: knobs.get(k) for k in ("speed_mul", "heat_mul", "collapse_mul")},
        "t_before": before.get("t"),
        "t_after": after.get("t"),
        "passed_before": int(bool(before.get("passed"))),
        "passed_after": int(bool(after.get("passed"))),
        "delta_t": round(float(after.get("t") or 0) - float(before.get("t") or 0), 4),
        "stored_prose": 0,
    }
