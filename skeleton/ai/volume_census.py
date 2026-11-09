"""Volume census on the AI plane.

Admits measured seals only. A projection is not a census.
Does not import the operator deck. Does not read emit trees.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

CLIP = 1.1
STORED_PROSE = 0
PROJECTION = 1_530_001_800
PIN = "dbe1aeb64225c7802e1b92ad61b24e19d8508b549be27dd2aa051f96157b51ee"
PAYLOAD = (
    "organ:3329408|masterplan:15302600|x10:153003200|"
    "x100_shard:7650009|eight:100800072|prose:0|clip:1.1"
)


@dataclass(frozen=True)
class Seal:
    name: str
    lines: int
    census: str


SEALS = (
    Seal("organ", 3_329_408, "census.py"),
    Seal("masterplan", 15_302_600, "wc"),
    Seal("x10", 153_003_200, "wc"),
    Seal("x100_shard", 7_650_009, "wc"),
    Seal("eight", 100_800_072, "wc"),
)


def claimed_lines() -> int:
    return sum(seal.lines for seal in SEALS)


def pin() -> str:
    digest = hashlib.sha256(PAYLOAD.encode()).hexdigest()
    if digest != PIN:
        raise RuntimeError("pin drift")
    return digest


def clip_mass(proposed: float, prior: float) -> float:
    if prior <= 0 or proposed < 0:
        raise ValueError("mass")
    ceiling = prior * CLIP
    return ceiling if proposed > ceiling else proposed


def admit(quoted: int) -> dict[str, object]:
    if quoted == PROJECTION:
        raise RuntimeError("projection is not a census")
    if quoted != claimed_lines():
        raise RuntimeError("unknown count")
    return {
        "plane": "ai",
        "url": "pointer://ai/volume/census",
        "claimed": quoted,
        "pin": pin(),
        "stored_prose": STORED_PROSE,
        "clip": CLIP,
        "x100_full": False,
    }
