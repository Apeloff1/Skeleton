"""Telegraph readability spec and auditor.

A telegraph is the promise an enemy makes before it hurts the player. The
contract enforced here: *every hit that matters is readable, reactable, and
punishable*. Rules scale with :class:`ThreatTier`:

=========  ===========  ==========  ===================  ==============
Tier       Min windup   Channels    Max dmg (% max HP)   Min recovery
=========  ===========  ==========  ===================  ==============
MINOR      300 ms       1           15 %                 0
MAJOR      600 ms       2           45 %                 30 % of windup
LETHAL     1200 ms      2 + audio   unbounded            50 % of windup
=========  ===========  ==========  ===================  ==============

Every telegraph with an area must also be *escapable*: human reaction time plus
the time to run out of the area must fit inside the windup.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import FrozenSet, Iterable, List, Sequence, Tuple, Union

HUMAN_REACTION_MS = 250
DEFAULT_MOVE_SPEED_MPS = 6.0
MAX_ACTIVE_MS = 1000
MAX_PHASE_MS = 10_000
MIN_PATTERN_GAP_MS = 400


class ThreatTier(str, Enum):
    MINOR = "minor"
    MAJOR = "major"
    LETHAL = "lethal"


class TelegraphChannel(str, Enum):
    BODY_ANIM = "body_anim"
    GROUND_DECAL = "ground_decal"
    AUDIO = "audio"
    UI_CAST_BAR = "ui_cast_bar"
    VFX_GLOW = "vfx_glow"


@dataclass(frozen=True)
class TierRule:
    min_windup_ms: int
    min_channels: int
    requires_audio: bool
    max_damage_fraction: float
    min_recovery_ratio: float


TIER_RULES = {
    ThreatTier.MINOR: TierRule(300, 1, False, 0.15, 0.0),
    ThreatTier.MAJOR: TierRule(600, 2, False, 0.45, 0.30),
    ThreatTier.LETHAL: TierRule(1200, 2, True, float("inf"), 0.50),
}


@dataclass(frozen=True)
class AttackTelegraph:
    name: str
    tier: ThreatTier
    windup_ms: int
    active_ms: int
    recovery_ms: int
    channels: FrozenSet[TelegraphChannel]
    damage_fraction: float
    escape_distance_m: float = 0.0
    persistent_zone: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name or len(self.name) > 64:
            raise ValueError("bad telegraph name")
        if not isinstance(self.tier, ThreatTier):
            raise ValueError("tier must be ThreatTier")
        for label, value in (("windup", self.windup_ms), ("active", self.active_ms), ("recovery", self.recovery_ms)):
            if isinstance(value, bool) or not isinstance(value, int) or not (0 <= value <= MAX_PHASE_MS):
                raise ValueError(f"{label}_ms out of bounds")
        if self.active_ms == 0:
            raise ValueError("active_ms must be > 0")
        if not isinstance(self.channels, frozenset) or not all(isinstance(c, TelegraphChannel) for c in self.channels):
            raise ValueError("channels must be TelegraphChannel")
        if type(self.persistent_zone) is not bool:
            raise ValueError("persistent_zone must be boolean")
        for value in (self.damage_fraction, self.escape_distance_m):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError("telegraph numeric fields must be finite numbers")
        if not (0.0 <= self.damage_fraction <= 5.0):
            raise ValueError("damage_fraction out of bounds")
        if not (0.0 <= self.escape_distance_m <= 100.0):
            raise ValueError("escape distance out of bounds")

    @property
    def total_ms(self) -> int:
        return self.windup_ms + self.active_ms + self.recovery_ms

    def scaled(self, windup_scale: float, damage_scale: float) -> "AttackTelegraph":
        """Return a difficulty-scaled copy.

        Difficulty may shorten windups, but never below the tier floor for an
        attack that was authored readable. An attack authored *below* its floor
        stays below it, so scaling never hides an authoring violation.
        """

        if not (0.25 <= windup_scale <= 4.0 and 0.1 <= damage_scale <= 5.0):
            raise ValueError("scale out of bounds")
        floor = TIER_RULES[self.tier].min_windup_ms
        windup = min(MAX_PHASE_MS, int(round(self.windup_ms * windup_scale)))
        if self.windup_ms >= floor:
            windup = max(floor, windup)
        return AttackTelegraph(
            self.name,
            self.tier,
            windup,
            self.active_ms,
            self.recovery_ms,
            self.channels,
            min(5.0, self.damage_fraction * damage_scale),
            self.escape_distance_m,
            self.persistent_zone,
        )


@dataclass(frozen=True)
class Violation:
    code: str
    subject: str
    message: str


def escape_time_ms(distance_m: float, move_speed_mps: float = DEFAULT_MOVE_SPEED_MPS) -> int:
    if move_speed_mps <= 0:
        raise ValueError("move speed must be > 0")
    if distance_m < 0:
        raise ValueError("distance must be >= 0")
    return int(round(1000.0 * distance_m / move_speed_mps))


def required_reaction_budget_ms(t: AttackTelegraph, move_speed_mps: float = DEFAULT_MOVE_SPEED_MPS) -> int:
    """Minimum windup a human needs to avoid this attack."""

    return HUMAN_REACTION_MS + escape_time_ms(t.escape_distance_m, move_speed_mps)


def audit_telegraph(t: AttackTelegraph, *, move_speed_mps: float = DEFAULT_MOVE_SPEED_MPS) -> List[Violation]:
    rule = TIER_RULES[t.tier]
    out: List[Violation] = []
    if t.windup_ms < rule.min_windup_ms:
        out.append(Violation("windup_below_tier_floor", t.name, f"{t.windup_ms}ms < {rule.min_windup_ms}ms for {t.tier.value}"))
    if len(t.channels) < rule.min_channels:
        out.append(Violation("too_few_channels", t.name, f"{len(t.channels)} < {rule.min_channels} channels"))
    if rule.requires_audio and TelegraphChannel.AUDIO not in t.channels:
        out.append(Violation("lethal_without_audio", t.name, "lethal telegraphs must carry an audio cue"))
    if t.damage_fraction > rule.max_damage_fraction:
        out.append(
            Violation(
                "damage_exceeds_tier",
                t.name,
                f"{t.damage_fraction:.2f} of max HP exceeds {t.tier.value} ceiling {rule.max_damage_fraction:.2f}; promote the tier",
            )
        )
    if t.recovery_ms < rule.min_recovery_ratio * t.windup_ms:
        out.append(Violation("no_punish_window", t.name, f"recovery {t.recovery_ms}ms < {rule.min_recovery_ratio:.0%} of windup"))
    if t.active_ms > MAX_ACTIVE_MS and not t.persistent_zone:
        out.append(Violation("active_too_long", t.name, f"active {t.active_ms}ms > {MAX_ACTIVE_MS}ms without persistent_zone"))
    need = required_reaction_budget_ms(t, move_speed_mps)
    if t.escape_distance_m > 0 and t.windup_ms < need:
        out.append(Violation("unescapable", t.name, f"windup {t.windup_ms}ms < reaction+escape {need}ms"))
    return out


@dataclass(frozen=True)
class PatternEntry:
    start_ms: int
    telegraph: AttackTelegraph

    @property
    def windup_window(self) -> Tuple[int, int]:
        return (self.start_ms, self.start_ms + self.telegraph.windup_ms)

    @property
    def resolve_ms(self) -> int:
        return self.start_ms + self.telegraph.windup_ms + self.telegraph.active_ms


def audit_pattern(entries: Sequence[PatternEntry], *, move_speed_mps: float = DEFAULT_MOVE_SPEED_MPS) -> List[Violation]:
    """Audit an attack rotation: per-telegraph rules plus cross-telegraph clarity.

    * Two MAJOR+ windups may not overlap (the player can read one big threat at a time).
    * After a LETHAL resolves, no new windup may start for ``MIN_PATTERN_GAP_MS``
      (breathing room after a lethal check).
    """

    out: List[Violation] = []
    ordered = sorted(entries, key=lambda e: e.start_ms)
    for entry in ordered:
        if entry.start_ms < 0:
            out.append(Violation("negative_start", entry.telegraph.name, "pattern entries start at >= 0"))
        out.extend(audit_telegraph(entry.telegraph, move_speed_mps=move_speed_mps))
    big = [e for e in ordered if e.telegraph.tier is not ThreatTier.MINOR]
    for i, a in enumerate(big):
        for b in big[i + 1 :]:
            a0, a1 = a.windup_window
            b0, b1 = b.windup_window
            if a0 < b1 and b0 < a1:
                out.append(
                    Violation("overlapping_major_windups", f"{a.telegraph.name}+{b.telegraph.name}", "two MAJOR+ windups overlap")
                )
    for i, a in enumerate(ordered):
        if a.telegraph.tier is not ThreatTier.LETHAL:
            continue
        resolve = a.resolve_ms
        for j, b in enumerate(ordered):
            if j == i:
                continue
            if resolve <= b.start_ms < resolve + MIN_PATTERN_GAP_MS:
                out.append(
                    Violation(
                        "no_breather_after_lethal",
                        f"{a.telegraph.name}->{b.telegraph.name}",
                        f"next windup within {MIN_PATTERN_GAP_MS}ms of lethal resolve",
                    )
                )
    return out


def is_readable(subject: Union[AttackTelegraph, Iterable[PatternEntry]]) -> bool:
    if isinstance(subject, AttackTelegraph):
        return not audit_telegraph(subject)
    return not audit_pattern(list(subject))
