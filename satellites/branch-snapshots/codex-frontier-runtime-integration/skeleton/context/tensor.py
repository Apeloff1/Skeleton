"""10-axis ContextTensor — the cube every other substrate reads.

Axes are named, unit-interval, and compose by lerp / Chebyshev / cosine.
An era dialect stamps a profile; the cockpit may nick individual axes;
the dodecahedron lights faces from the same vector; Jeeves weights
advice off it. Nothing in GameForge should carry a free-floating float
that does not live on this cube.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Tuple

AXES: Tuple[str, ...] = (
    "risk", "tempo", "lethality", "opacity", "scarcity",
    "agency", "spectacle", "intimacy", "grind", "authorial",
)

ERA_PROFILES: Dict[str, Dict[str, float]] = {
    "extraction_now":     dict(risk=0.82, tempo=0.70, lethality=0.68, opacity=0.55, scarcity=0.80, agency=0.75, spectacle=0.45, intimacy=0.30, grind=0.55, authorial=0.40),
    "soulslike":          dict(risk=0.88, tempo=0.45, lethality=0.90, opacity=0.70, scarcity=0.75, agency=0.60, spectacle=0.35, intimacy=0.40, grind=0.85, authorial=0.80),
    "boomer_shooter":     dict(risk=0.70, tempo=0.95, lethality=0.85, opacity=0.25, scarcity=0.40, agency=0.90, spectacle=0.80, intimacy=0.15, grind=0.25, authorial=0.35),
    "arcade_golden_age":  dict(risk=0.60, tempo=0.92, lethality=0.55, opacity=0.10, scarcity=0.30, agency=0.50, spectacle=0.85, intimacy=0.10, grind=0.20, authorial=0.25),
    "cozy_wholesome":     dict(risk=0.12, tempo=0.30, lethality=0.08, opacity=0.15, scarcity=0.20, agency=0.55, spectacle=0.25, intimacy=0.90, grind=0.15, authorial=0.50),
    "modern_aaa":         dict(risk=0.45, tempo=0.60, lethality=0.55, opacity=0.35, scarcity=0.40, agency=0.50, spectacle=0.75, intimacy=0.45, grind=0.50, authorial=0.30),
    "horror_survival":    dict(risk=0.90, tempo=0.35, lethality=0.70, opacity=0.85, scarcity=0.90, agency=0.40, spectacle=0.40, intimacy=0.55, grind=0.45, authorial=0.70),
    "indie_experimental": dict(risk=0.55, tempo=0.65, lethality=0.50, opacity=0.60, scarcity=0.50, agency=0.85, spectacle=0.55, intimacy=0.50, grind=0.30, authorial=0.95),
}

_ERA_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "soulslike": ("soul", "bonfire", "estus", "i-frame", "iframe", "poise", "sekiro", "bloodborne"),
    "boomer_shooter": ("boomer", "quake", "doom", "gib", "rocket jump", "arena fps"),
    "arcade_golden_age": ("arcade", "high score", "1-up", "galaga", "pac-man", "cabinet"),
    "cozy_wholesome": ("cozy", "wholesome", "stardew", "cottage", "low stress", "farming"),
    "horror_survival": ("horror", "resident", "silent hill", "ammo scarce", "dread"),
    "modern_aaa": ("aaa", "cover shooter", "ubisoft", "cinematic"),
    "indie_experimental": ("indie", "experimental", "authorial", "twine", "zachlike"),
    "extraction_now": ("extract", "tarkov", "dmz", "raid", "loot", "heat", "collapse"),
    "metroidvania": ("metroid", "vania", "ability gate", "backtrack", "map unlock"),
    "roguelike": ("roguelike", "permadeath", "procgen", "dcss", "nethack"),
    "jrpg": ("jrpg", "turn-based", "materia", "atb", "final fantasy"),
    "crpg": ("crpg", "baldur", "infinity engine", "isometric party"),
    "immersive_sim": ("immersive sim", "deus ex", "dishonored", "systemic"),
    "stealth": ("stealth", "metal gear", "mark and execute", "undetected"),
    "tactics_grid": ("tactics", "grid", "xcom", "fire emblem", "cover chance"),
    "fighting_game": ("fighting game", "footsies", "frame data", "combo"),
    "bullet_heaven": ("bullet heaven", "survivor-like", "vampire survivors", "horde"),
    "deckbuilder": ("deckbuilder", "slay the spire", "card pile", "energy cost"),
    "battle_royale": ("battle royale", "zone close", "drop ship", "last standing"),
    "mmorpg": ("mmorpg", "raid night", "subscription", "auction house"),
    "visual_novel": ("visual novel", "renpy", "dialogue tree", "cg route"),
    "walking_sim": ("walking sim", "gone home", "what remains", "environmental story"),
    "grand_strategy": ("grand strategy", "europa universalis", "ck3", "pdx"),
    "city_builder": ("city builder", "simcity", "zoning", "traffic sim"),
}


def _clamp(v: float) -> float:
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else float(v)


@dataclass
class ContextTensor:
    """A point on the unit 10-cube. Frozen after construction; use lerp/with_axis."""

    values: Tuple[float, ...]
    era: str = "extraction_now"

    def __post_init__(self) -> None:
        if len(self.values) != len(AXES):
            raise ValueError(f"tensor rank {len(self.values)} != {len(AXES)}")
        object.__setattr__(self, "values", tuple(_clamp(v) for v in self.values))

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, float], *, era: str = "extraction_now") -> "ContextTensor":
        return cls(tuple(float(mapping.get(a, 0.5)) for a in AXES), era=era)

    @classmethod
    def from_era(cls, era: str) -> "ContextTensor":
        if era in ERA_PROFILES:
            return cls.from_mapping(ERA_PROFILES[era], era=era)
        from skeleton.forge.eras import ERA_IDS, compile_era
        if era in ERA_IDS:
            pack = compile_era(era)
            speed = float(pack["player"]["speed"])
            glass = float(pack["ttk"]["player_glass"])
            trash = float(pack["ttk"]["trash"])
            perm = float(pack["meta"].get("permadeath") or 0.5)
            mapping = {
                "risk": perm,
                "tempo": min(1.0, speed / 240.0),
                "lethality": min(1.0, 2.0 / max(glass, 0.2)),
                "opacity": min(1.0, trash / 8.0),
                "scarcity": perm * 0.8 + 0.1,
                "agency": min(1.0, speed / 200.0),
                "spectacle": min(1.0, 1.2 - trash / 10.0),
                "intimacy": max(0.0, 1.0 - perm),
                "grind": min(1.0, float(pack["ttk"]["boss"]) / 200.0),
                "authorial": 0.55,
            }
            return cls.from_mapping(mapping, era=era)
        return cls.from_mapping(ERA_PROFILES["extraction_now"], era="extraction_now")

    def as_dict(self) -> Dict[str, float]:
        return {a: round(v, 4) for a, v in zip(AXES, self.values)}

    def __getitem__(self, axis: str) -> float:
        return self.values[AXES.index(axis)]

    def with_axis(self, axis: str, value: float) -> "ContextTensor":
        i = AXES.index(axis)
        vals = list(self.values)
        vals[i] = _clamp(value)
        return ContextTensor(tuple(vals), era=self.era)

    def lerp(self, other: "ContextTensor", t: float) -> "ContextTensor":
        t = _clamp(t)
        vals = tuple(a + (b - a) * t for a, b in zip(self.values, other.values))
        era = self.era if t < 0.5 else other.era
        return ContextTensor(vals, era=era)

    def manhattan(self, other: "ContextTensor") -> float:
        return sum(abs(a - b) for a, b in zip(self.values, other.values))

    def euclidean(self, other: "ContextTensor") -> float:
        return math.sqrt(sum((a - b) ** 2 for a, b in zip(self.values, other.values)))

    def chebyshev(self, other: "ContextTensor") -> float:
        return max(abs(a - b) for a, b in zip(self.values, other.values))

    def cosine(self, other: "ContextTensor") -> float:
        dot = sum(a * b for a, b in zip(self.values, other.values))
        na = math.sqrt(sum(a * a for a in self.values))
        nb = math.sqrt(sum(b * b for b in other.values))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def fingerprint(self) -> str:
        raw = ",".join(f"{v:.4f}" for v in self.values) + "|" + self.era
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def dominant(self, n: int = 3) -> List[Tuple[str, float]]:
        ranked = sorted(zip(AXES, self.values), key=lambda kv: -kv[1])
        return ranked[:n]

    def to_dict(self) -> Dict[str, object]:
        return {
            "era": self.era,
            "axes": self.as_dict(),
            "dominant": [{"axis": a, "value": round(v, 4)} for a, v in self.dominant()],
            "fingerprint": self.fingerprint(),
        }


def detect_era(text: str) -> Tuple[str, Dict[str, int]]:
    """Keyword vote. Ties fall back to extraction_now."""
    blob = (text or "").lower()
    scores = {era: sum(1 for kw in kws if kw in blob) for era, kws in _ERA_KEYWORDS.items()}
    winner = max(scores, key=lambda e: scores[e])
    if scores[winner] == 0:
        return "extraction_now", scores
    return winner, scores
