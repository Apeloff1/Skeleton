"""Colored Hoag mirrors — one ring per LLM connector in the cortex.

Every catalog family and every house slot gets a satellite ring in
the dark gap. Jeeves is the only bridge: mouths never write the
nucleus directly. Color is deterministic from family id.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from skeleton.galaxy.hoag import GAP, ring_points


def _families():
    from skeleton.cortex.catalog import FAMILIES
    return FAMILIES


HOUSE_SLOTS = ("pfc", "mid", "left", "right", "neo", "neo_rms")

_PALETTE = (
    "#4EC8C8", "#E8A03A", "#8B6BFF", "#F0C040", "#8FA37A",
    "#C46B6B", "#6BA3C4", "#C48F6B", "#6BC48F", "#A36BC4",
    "#C4C46B", "#6B8FC4",
)


def _color(key: str) -> str:
    h = int(hashlib.sha256(key.encode("utf-8")).hexdigest()[:8], 16)
    return _PALETTE[h % len(_PALETTE)]


def mouth_mirrors() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for fam in _families():
        fid = str(fam["id"])
        rows.append({
            "id": fid,
            "house": fam.get("house"),
            "gate": fam.get("gate"),
            "models": list(fam.get("models") or ()),
            "color": _color(fid),
            "zone": "gap",
            "ring": GAP["ring"],
            "via": "jeeves",
        })
    for slot in HOUSE_SLOTS:
        rows.append({
            "id": f"house.{slot}",
            "house": "Skeleton",
            "gate": "local",
            "models": [slot],
            "color": _color(slot),
            "zone": "gap",
            "ring": GAP["ring"],
            "via": "jeeves",
        })
    return rows


def bind_mouth(family_id: str) -> Dict[str, Any]:
    for row in mouth_mirrors():
        if row["id"] == family_id or family_id in row["models"]:
            return {**row, "bound": 1, "stored_prose": 0}
    return {
        "id": family_id,
        "bound": 0,
        "color": _color(family_id),
        "via": "jeeves",
        "stored_prose": 0,
    }


def gap_lattice(n: int = 12) -> List[Dict[str, Any]]:
    pts = ring_points("wiki", n=n, tilt=0.22)
    mouths = mouth_mirrors()
    out = []
    for i, p in enumerate(pts):
        m = mouths[i % len(mouths)]
        d = p.to_dict()
        d["mouth"] = m["id"]
        d["color"] = m["color"]
        out.append(d)
    return out
