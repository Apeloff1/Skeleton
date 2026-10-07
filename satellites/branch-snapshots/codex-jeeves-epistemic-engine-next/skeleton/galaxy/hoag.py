"""Hoag galaxy — nucleus, dark gap, colored rings.

Hoag's Object is a yellow older core ringed by a younger blue star
ring, separated by a dark annulus. House knowledge uses the same
topology: wiki librarian as nucleus, five brains as colored rings,
LLM mouths as satellite rings in the gap. Geometry is discrete
(not a raster of NASA pixels). Cite the object; do not copy captions.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

PHI = (1.0 + math.sqrt(5.0)) / 2.0

# Pointer only — no Hubble caption prose.
HOAG_CITE = {
    "title": "Hoag's Object",
    "url": "https://science.nasa.gov/image-detail/idl-tiff-file-43/",
    "license": "NASA/Hubble Heritage (STScI/AURA) image credit",
    "stored_prose": 0,
}

BRAINS: Tuple[Dict[str, Any], ...] = (
    {"id": "memory", "ordinal": 1, "role": "capture-episodic", "color": "#4EC8C8", "ring": 1.00},
    {"id": "compiler", "ordinal": 2, "role": "second-brain-compile", "color": "#E8A03A", "ring": 1.18},
    {"id": "dream", "ordinal": 3, "role": "offline-consolidation", "color": "#8B6BFF", "ring": 1.36},
    {"id": "distiller", "ordinal": 4, "role": "principles-rules", "color": "#F0C040", "ring": 1.54},
    {"id": "editor", "ordinal": 5, "role": "traffic-master-index", "color": "#8FA37A", "ring": 1.72},
)

NUCLEUS = {"id": "wiki", "role": "wiki-librarian", "color": "#D4A84B", "ring": 0.28}
GAP = {"id": "gap", "role": "mouth-mirrors", "color": "#0C0C0B", "ring": 0.62}


def color_of(brain: str) -> str:
    if brain == "wiki" or brain == "nucleus":
        return str(NUCLEUS["color"])
    for row in BRAINS:
        if row["id"] == brain:
            return str(row["color"])
    return "#8FA37A"


def ring_of(brain: str) -> float:
    if brain == "wiki" or brain == "nucleus":
        return float(NUCLEUS["ring"])
    for row in BRAINS:
        if row["id"] == brain:
            return float(row["ring"])
    return 1.0


@dataclass(frozen=True)
class HoagPoint:
    x: float
    y: float
    z: float
    brain: str
    color: str

    def to_dict(self) -> Dict[str, Any]:
        return {"x": round(self.x, 5), "y": round(self.y, 5), "z": round(self.z, 5),
                "brain": self.brain, "color": self.color}


def ring_points(brain: str, n: int = 24, tilt: float = 0.18) -> List[HoagPoint]:
    r = ring_of(brain)
    c = color_of(brain)
    pts: List[HoagPoint] = []
    for i in range(max(3, n)):
        th = (2.0 * math.pi * i) / n
        x = r * math.cos(th)
        y = r * math.sin(th) * math.cos(tilt)
        z = r * math.sin(th) * math.sin(tilt) / PHI
        pts.append(HoagPoint(x, y, z, brain, c))
    return pts


def nucleus_points(n: int = 8) -> List[HoagPoint]:
    return ring_points("wiki", n=n, tilt=0.08)


def galaxy_card() -> Dict[str, Any]:
    return {
        "kind": "hoag-galaxy",
        "cite": dict(HOAG_CITE),
        "nucleus": dict(NUCLEUS),
        "gap": dict(GAP),
        "brains": [dict(b) for b in BRAINS],
        "rings": len(BRAINS),
        "stored_prose": 0,
    }
