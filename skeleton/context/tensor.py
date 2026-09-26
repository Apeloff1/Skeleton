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
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ValueError("axis value must be a finite number")
    number = float(v)
    if not math.isfinite(number):
        raise ValueError("axis value must be a finite number")
    return 0.0 if number < 0.0 else 1.0 if number > 1.0 else number


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
    def from_mapping(cls, mapping: Mapping[str, float], *, era: str) -> "ContextTensor":
        if not isinstance(era, str) or not era.strip():
            raise ValueError("era is required")
        if not isinstance(mapping, Mapping):
            raise TypeError("tensor mapping is required")
        missing = [axis for axis in AXES if axis not in mapping]
        if missing:
            raise ValueError("tensor mapping is missing " + ", ".join(missing))
        return cls(tuple(mapping[axis] for axis in AXES), era=era)

    @classmethod
    def from_era(cls, era: str) -> "ContextTensor":
        if not isinstance(era, str) or not era.strip():
            raise ValueError("era is required")
        if era in ERA_PROFILES:
            return cls.from_mapping(ERA_PROFILES[era], era=era)
        from skeleton.forge.eras import ERA_IDS, compile_era
        if era not in ERA_IDS:
            raise ValueError(f"unknown era {era!r}")
        pack = compile_era(era)
        try:
            speed = pack["player"]["speed"]
            glass = pack["ttk"]["player_glass"]
            trash = pack["ttk"]["trash"]
            boss = pack["ttk"]["boss"]
            perm = pack["meta"]["permadeath"]
        except (KeyError, TypeError) as exc:
            raise ValueError(f"era {era!r} pack does not measure a cube") from exc
        measured = {
            "speed": speed,
            "player_glass": glass,
            "trash": trash,
            "boss": boss,
            "permadeath": perm,
        }
        for name, value in measured.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"era {era!r} {name} is not a finite number")
        speed_f = float(speed)
        glass_f = float(glass)
        trash_f = float(trash)
        boss_f = float(boss)
        perm_f = float(perm)
        if glass_f <= 0.0 or speed_f < 0.0 or trash_f < 0.0 or boss_f < 0.0 or not 0.0 <= perm_f <= 1.0:
            raise ValueError(f"era {era!r} pack is not a usable cube")
        # The pack has no authorial sensor. A derived cube may not invent one.
        authorial = pack["meta"].get("authorial") if isinstance(pack.get("meta"), dict) else None
        if isinstance(authorial, bool) or not isinstance(authorial, (int, float)) or not math.isfinite(float(authorial)):
            raise ValueError(f"era {era!r} does not measure authorial")
        mapping = {
            "risk": perm_f,
            "tempo": min(1.0, speed_f / 240.0),
            "lethality": min(1.0, 2.0 / glass_f),
            "opacity": min(1.0, trash_f / 8.0),
            "scarcity": perm_f * 0.8 + 0.1,
            "agency": min(1.0, speed_f / 200.0),
            "spectacle": min(1.0, 1.2 - trash_f / 10.0),
            "intimacy": max(0.0, 1.0 - perm_f),
            "grind": min(1.0, boss_f / 200.0),
            "authorial": float(authorial),
        }
        return cls.from_mapping(mapping, era=era)

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
        if not isinstance(other, ContextTensor):
            raise TypeError("lerp target must be a context cube")
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(float(t)):
            raise ValueError("lerp t must be in [0, 1]")
        blend = float(t)
        if not 0.0 <= blend <= 1.0:
            raise ValueError("lerp t must be in [0, 1]")
        vals = tuple(a + (b - a) * blend for a, b in zip(self.values, other.values))
        era = self.era if blend < 0.5 else other.era
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
            raise ValueError("cosine is undefined for a zero cube")
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
    """Keyword vote. A blank, unmatched, or tied observation is not an era."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("observation is required")
    blob = text.lower()
    scores = {era: sum(1 for kw in kws if kw in blob) for era, kws in _ERA_KEYWORDS.items()}
    best = max(scores.values())
    if best <= 0:
        raise ValueError("observation did not match an era")
    winners = [era for era, score in scores.items() if score == best]
    if len(winners) != 1:
        raise ValueError("observation matched more than one era: " + ", ".join(sorted(winners)))
    return winners[0], scores
