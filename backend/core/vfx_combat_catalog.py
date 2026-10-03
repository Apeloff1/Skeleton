"""Era combat VFX catalog + readability rules.

Extends :mod:`core.vfx_cues` (it never modifies it): every era defined in
:mod:`core.eras` gets a combat cue set (hit spark, crit, telegraph, death,
pickup) sized to that era's real envelope, plus pure readability rules a forge
or renderer can gate on:

* telegraph lead time must grow with the share of health an attack removes,
* every cue type has a duration window (too short is unreadable, too long
  smears the next beat),
* each frame has an effect-count and particle budget; telegraphs are admitted
  first so a busy frame never hides an incoming hit,
* all telegraph/danger colouring goes through one semantic ramp
  (:data:`DANGER_RAMP`, low → lethal) keyed by the same damage share that sets
  the lead-time floor, so the HUD can share the same tiers.

Cues may carry an optional ``hit_frame`` (animation contact frame) so impact
VFX can be keyed to the frame where a strike actually lands.

Pixel eras (no polygons) are locked to whole 60 Hz frames and their particle
budget is the era's hardware sprite limit (``max_sprites``). Cue colour counts
are checked against the era's ``colors_max``. The eras module exposes colour
counts, not palette values, so no contrast math is done here.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import ceil
from typing import Iterable

from core.eras import ERA_ORDER, ERAS, get_era
from core.vfx_cues import BurstEvent, VfxState

CUE_TYPES: tuple[str, ...] = ("hit_spark", "crit", "telegraph", "death", "pickup")
TELEGRAPH_SHAPES: tuple[str, ...] = ("circle", "cone", "line", "ring")

# Readable duration window per cue type, inclusive, in milliseconds.
DURATION_WINDOWS_MS: dict[str, tuple[int, int]] = {
    "hit_spark": (50, 180),
    "crit": (120, 350),
    "telegraph": (250, 1500),
    "death": (300, 900),
    "pickup": (150, 450),
}

# Telegraph lead floor: a chip hit needs BASE, a hit that removes the target's
# whole health bar needs BASE + SCALE.
TELEGRAPH_LEAD_BASE_MS = 250
TELEGRAPH_LEAD_SCALE_MS = 650



@dataclass(frozen=True, slots=True)
class DangerTier:
    """Semantic danger level. ``max_share`` is the upper bound (inclusive) of
    the damage / max-health share this tier covers; ``colors`` is how many
    colours of the era palette a telegraph at this tier may use."""

    name: str
    max_share: float
    colors: int


# The one danger mapping, ordered low → lethal. Renderers and HUD resolve the
# semantic names to actual palette entries; no RGB values live here.
DANGER_RAMP: tuple[DangerTier, ...] = (
    DangerTier("low", 0.25, 1),
    DangerTier("moderate", 0.50, 2),
    DangerTier("high", 0.85, 3),
    DangerTier("lethal", 1.00, 4),
)
DANGER_TIERS: tuple[str, ...] = tuple(t.name for t in DANGER_RAMP)

# Admission order when a frame is over budget (lower index wins).
CUE_PRIORITY: tuple[str, ...] = ("telegraph", "crit", "death", "hit_spark", "pickup")

FRAME_MS_60HZ = 1000.0 / 60.0

# Per-frame caps: (max concurrent effects, particle budget). Pixel eras take the
# particle budget from the era's sprite limit instead of this table.
_FRAME_BUDGET: dict[str, tuple[int, int]] = {
    "8bit": (6, 0),
    "16bit": (10, 0),
    "early3d": (16, 256),
    "64bit": (24, 512),
    "earlyhd": (32, 1024),
    "modern": (48, 4096),
    "nextgen": (64, 8192),
}

# Base cue design (modern-era reference): duration_ms, particles, colours,
# screen trauma, burst intensity.
_BASE_CUES: dict[str, tuple[int, int, int, float, float]] = {
    "hit_spark": (110, 24, 3, 0.10, 0.6),
    "crit": (220, 48, 4, 0.35, 1.0),
    "telegraph": (450, 16, 2, 0.0, 0.5),
    "death": (600, 64, 4, 0.45, 1.0),
    "pickup": (280, 20, 3, 0.0, 0.7),
}

# Per-era particle scale relative to the modern reference, and default
# telegraph shape (pixel eras read best as straight lanes / boxes on a grid).
_ERA_STYLE: dict[str, tuple[float, str]] = {
    "8bit": (0.125, "line"),
    "16bit": (0.25, "line"),
    "early3d": (0.5, "circle"),
    "64bit": (0.75, "circle"),
    "earlyhd": (1.0, "cone"),
    "modern": (1.0, "cone"),
    "nextgen": (1.5, "cone"),
}


@dataclass(frozen=True, slots=True)
class CombatCue:
    era: str
    cue_type: str
    duration_ms: int
    particles: int
    colors: int
    trauma: float
    intensity: float
    shape: str | None = None
    lead_ms: int | None = None
    severity: str | None = None
    hit_frame: int | None = None


@dataclass(frozen=True, slots=True)
class FrameBudget:
    max_effects: int
    max_particles: int


@dataclass(frozen=True, slots=True)
class FramePlan:
    admitted: tuple[CombatCue, ...]
    dropped: tuple[CombatCue, ...]

    @property
    def particles(self) -> int:
        return sum(c.particles for c in self.admitted)


def is_pixel_era(era_key: str) -> bool:
    return ERAS[era_key]["max_poly"] == 0


def frame_lock_ms(ms: float) -> int:
    """Snap a duration to a whole number of 60 Hz frames (at least one)."""
    frames = max(1, round(ms / FRAME_MS_60HZ))
    return round(frames * FRAME_MS_60HZ)


def damage_share(damage: float, max_health: float) -> float:
    """Share of the target's health an attack removes, clamped to [0, 1]."""
    if max_health <= 0:
        raise ValueError("max_health must be positive")
    if damage < 0:
        raise ValueError("damage cannot be negative")
    return min(1.0, damage / max_health)


def tier_for_share(share: float) -> DangerTier:
    if not 0.0 <= share <= 1.0:
        raise ValueError("share must be within [0, 1]")
    for tier in DANGER_RAMP:
        if share <= tier.max_share:
            return tier
    return DANGER_RAMP[-1]


def danger_tier(damage: float, max_health: float) -> DangerTier:
    """Danger tier from the same damage share that drives the lead-time floor."""
    return tier_for_share(damage_share(damage, max_health))


def danger_tier_named(name: str) -> DangerTier:
    for tier in DANGER_RAMP:
        if tier.name == name:
            return tier
    raise ValueError(f"unknown danger tier: {name}")


def share_covered_by_lead(lead_ms: int) -> float:
    """Largest damage share whose lead-time floor ``lead_ms`` still satisfies."""
    return max(0.0, min(1.0, (lead_ms - TELEGRAPH_LEAD_BASE_MS) / TELEGRAPH_LEAD_SCALE_MS))


def _check_hit_frame(hit_frame: int | None) -> int | None:
    if hit_frame is not None and hit_frame < 0:
        raise ValueError("hit_frame must be >= 0")
    return hit_frame


def frame_budget(era_key: str | None) -> FrameBudget:
    era = get_era(era_key)
    max_effects, particles = _FRAME_BUDGET[era["key"]]
    if era["max_poly"] == 0:
        particles = era["max_sprites"]
    return FrameBudget(max_effects=max_effects, max_particles=particles)


def _build_cue(era_key: str, cue_type: str) -> CombatCue:
    duration, particles, colors, trauma, intensity = _BASE_CUES[cue_type]
    scale, shape = _ERA_STYLE[era_key]
    budget = frame_budget(era_key)
    count = max(1, min(round(particles * scale), budget.max_particles))
    if is_pixel_era(era_key):
        duration = frame_lock_ms(duration)
    is_telegraph = cue_type == "telegraph"
    severity = None
    if is_telegraph:
        tier = tier_for_share(share_covered_by_lead(duration))
        severity, colors = tier.name, tier.colors
    return CombatCue(
        era=era_key,
        cue_type=cue_type,
        duration_ms=duration,
        particles=count,
        colors=colors,
        trauma=trauma,
        intensity=intensity,
        shape=shape if is_telegraph else None,
        lead_ms=duration if is_telegraph else None,
        severity=severity,
    )


def build_catalog() -> dict[str, dict[str, CombatCue]]:
    return {era: {cue: _build_cue(era, cue) for cue in CUE_TYPES} for era in ERA_ORDER}


CATALOG: dict[str, dict[str, CombatCue]] = build_catalog()


def cue_for(era_key: str | None, cue_type: str) -> CombatCue:
    if cue_type not in CUE_TYPES:
        raise ValueError(f"unknown cue type: {cue_type}")
    return CATALOG[get_era(era_key)["key"]][cue_type]


# ── readability rules (pure) ────────────────────────────────────────────────

def min_telegraph_lead_ms(damage: float, max_health: float) -> int:
    """Lead-time floor for an attack: grows linearly with health share removed."""
    share = damage_share(damage, max_health)
    return round(TELEGRAPH_LEAD_BASE_MS + TELEGRAPH_LEAD_SCALE_MS * share)


def telegraph_lead_ok(lead_ms: int, damage: float, max_health: float) -> bool:
    return lead_ms >= min_telegraph_lead_ms(damage, max_health)


def duration_ok(cue_type: str, duration_ms: int) -> bool:
    if cue_type not in DURATION_WINDOWS_MS:
        raise ValueError(f"unknown cue type: {cue_type}")
    lo, hi = DURATION_WINDOWS_MS[cue_type]
    return lo <= duration_ms <= hi


def colors_ok(era_key: str | None, colors: int) -> bool:
    return 0 < colors <= get_era(era_key)["colors_max"]


def frame_budget_ok(cues: Iterable[CombatCue], era_key: str | None) -> bool:
    items = list(cues)
    budget = frame_budget(era_key)
    return len(items) <= budget.max_effects and sum(c.particles for c in items) <= budget.max_particles


def plan_frame(cues: Iterable[CombatCue], era_key: str | None) -> FramePlan:
    """Admit cues by readability priority until the era's frame budget is full."""
    budget = frame_budget(era_key)
    ordered = sorted(enumerate(cues), key=lambda ic: (CUE_PRIORITY.index(ic[1].cue_type), ic[0]))
    admitted: list[CombatCue] = []
    dropped: list[CombatCue] = []
    particles = 0
    for _, cue in ordered:
        if len(admitted) < budget.max_effects and particles + cue.particles <= budget.max_particles:
            admitted.append(cue)
            particles += cue.particles
        else:
            dropped.append(cue)
    return FramePlan(admitted=tuple(admitted), dropped=tuple(dropped))


def telegraph_for(
    era_key: str | None,
    damage: float,
    max_health: float,
    *,
    shape: str | None = None,
    hit_frame: int | None = None,
) -> CombatCue:
    """Era telegraph stretched to the lead floor this hit needs, coloured by its danger tier."""
    _check_hit_frame(hit_frame)
    base = cue_for(era_key, "telegraph")
    chosen = shape or base.shape
    if chosen not in TELEGRAPH_SHAPES:
        raise ValueError(f"unknown telegraph shape: {chosen}")
    lead = max(base.lead_ms or 0, min_telegraph_lead_ms(damage, max_health))
    if is_pixel_era(base.era):
        lead = round(ceil(lead / FRAME_MS_60HZ - 1e-9) * FRAME_MS_60HZ)
    lead = min(lead, DURATION_WINDOWS_MS["telegraph"][1])
    tier = danger_tier(damage, max_health)
    return replace(
        base,
        shape=chosen,
        lead_ms=lead,
        duration_ms=lead,
        severity=tier.name,
        colors=tier.colors,
        hit_frame=hit_frame,
    )


def with_hit_frame(cue: CombatCue, hit_frame: int | None) -> CombatCue:
    """Key any cue to an animation contact frame (or clear it with ``None``)."""
    return replace(cue, hit_frame=_check_hit_frame(hit_frame))


def validate_cue(cue: CombatCue) -> list[str]:
    failed: list[str] = []
    if cue.cue_type not in CUE_TYPES:
        return ["cue_type_known"]
    if not duration_ok(cue.cue_type, cue.duration_ms):
        failed.append("duration_in_window")
    if not colors_ok(cue.era, cue.colors):
        failed.append("colors_within_era")
    if cue.particles <= 0 or cue.particles > frame_budget(cue.era).max_particles:
        failed.append("particles_within_budget")
    if cue.cue_type == "telegraph":
        if cue.shape not in TELEGRAPH_SHAPES:
            failed.append("telegraph_shape_known")
        if cue.lead_ms is None or cue.lead_ms < TELEGRAPH_LEAD_BASE_MS:
            failed.append("telegraph_lead_floor")
        if cue.severity not in DANGER_TIERS:
            failed.append("telegraph_severity_known")
        elif cue.colors != danger_tier_named(cue.severity).colors:
            failed.append("telegraph_colors_match_ramp")
    elif cue.severity is not None:
        failed.append("severity_only_on_telegraph")
    if cue.hit_frame is not None and cue.hit_frame < 0:
        failed.append("hit_frame_non_negative")
    return failed


def validate_catalog(catalog: dict[str, dict[str, CombatCue]] | None = None) -> dict[str, list[str]]:
    """Return ``{era: [failure, ...]}`` for every era with a problem (empty = clean)."""
    data = CATALOG if catalog is None else catalog
    problems: dict[str, list[str]] = {}
    for era in ERA_ORDER:
        cues = data.get(era)
        if cues is None:
            problems[era] = ["era_missing"]
            continue
        failed = [f"{c}:missing" for c in CUE_TYPES if c not in cues]
        failed += [f"{c}:{f}" for c, cue in cues.items() for f in validate_cue(cue)]
        if failed:
            problems[era] = failed
    return problems


# ── bridge into the renderer-neutral VFX state ──────────────────────────────

def emit(
    state: VfxState,
    cue: CombatCue,
    x: float,
    y: float,
    z: float,
    *,
    frame: int | None = None,
) -> BurstEvent | None:
    """Fire a combat cue into :class:`VfxState` as a burst plus screen trauma.

    When the cue is keyed to a ``hit_frame`` and the current animation ``frame``
    is given, nothing fires (and ``None`` is returned) until they match.
    """
    _check_hit_frame(frame)
    if frame is not None and cue.hit_frame is not None and frame != cue.hit_frame:
        return None
    if cue.trauma > 0:
        state.add_trauma(cue.trauma)
    return state.emit_burst(x, y, z, count=cue.particles, intensity=cue.intensity)
