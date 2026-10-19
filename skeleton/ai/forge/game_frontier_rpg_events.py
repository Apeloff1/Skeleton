"""Advanced RPG event pages and environmental/instrument-triggered behaviors.

All triggers are evidence-based, ordered and proposal-only. Time/cooldown
state comes from the canonical save/runtime owner, not a second local ledger.
The event editor can author gameplay in ancient tile engines through 3D
worlds; actual NPC/quest/world mutations require existing engine approval.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Mapping


class RPGEventError(ValueError):
    pass


RPG_ENVIRONMENT_SIGNALS = frozenset((
    "temperature_c", "altitude_m", "pressure_pa", "humidity",
    "wind_mps", "updraft_mps", "turbulence_mps", "rain_mm_h",
    "fog_visibility_m", "water_depth_m", "tide_height_m",
    "moon_phase", "solar_height", "daylight", "shadow_fraction",
    "leaf_shadow_area_m2", "soil_wetness", "ground_ice_fraction",
    "erosion", "building_integrity", "character_mass_kg",
    "center_of_mass_offset_m", "support_margin_m", "impact_impulse_ns",
    "collision_energy_j", "fall_speed_mps", "traction_slip_risk",
    "climb_angle_deg", "garment_wetness", "skin_strain",
    "compass_heading_deg", "gyro_tilt_deg", "sextant_altitude_deg",
    "barometric_altitude_m", "trigonometric_altitude_m",
    "bubble_sextant_altitude_deg", "npc_reputation", "quest_progress",
    "party_morale", "music_intensity", "sound_occlusion",
    "sky_island_height_m",
    # Derived exclusively from independently replayed native physics ticks.
    "native_actor_speed_mps", "native_vertical_speed_mps",
    "native_contact_count", "native_kinetic_energy_j",
    "native_gameplay_zone_entries", "native_gameplay_zone_exits",
    "native_gameplay_zone_occupants",
    "native_gameplay_field_force_n",
    "native_gameplay_updraft_force_n",
))

ACTIONS = frozenset((
    "set_flag", "start_quest", "advance_quest", "show_dialogue",
    "play_cutscene", "play_music", "spatial_audio", "change_camera",
    "spawn_prefab", "despawn_prefab", "weather_transition",
    "world_portal", "change_light", "change_tide", "set_npc_emotion",
    "set_faction_reputation", "deform_terrain", "trigger_impact_fx",
    "trigger_foliage_fx", "apply_gameplay_effect", "craft_item",
    "open_shop", "unlock_skill", "start_combat", "save_bookmark",
    "take_damage", "heal_health", "consume_item", "award_xp",
    "inspect_instrument", "set_world_axis",
))

COMPARISONS = frozenset((
    "above", "below", "at_least", "at_most", "cross_up",
    "cross_down", "inside_range", "outside_range",
))
EVENT_CHANNELS = frozenset(("world", "audio", "quest", "character",
                            "environment", "cinematic", "ui", "navigation"))


def _bounded(value: float, name: str) -> float:
    if type(value) not in (float,int) or not math.isfinite(value) or abs(value) > 1e12:
        raise RPGEventError(f"{name} must be bounded finite number")
    return float(value)


@dataclass(frozen=True)
class EnvironmentalTrigger:
    signal: str
    comparison: str
    threshold: float
    upper_threshold: float | None = None
    hysteresis: float = 0.

    def __post_init__(self) -> None:
        if self.signal not in RPG_ENVIRONMENT_SIGNALS:
            raise RPGEventError("unsupported RPG environment signal")
        if self.comparison not in COMPARISONS:
            raise RPGEventError("unsupported comparator")
        _bounded(self.threshold, "threshold")
        _bounded(self.hysteresis, "hysteresis")
        if self.hysteresis < 0:
            raise RPGEventError("negative hysteresis")
        if self.comparison in ("inside_range","outside_range"):
            if self.upper_threshold is None or not self.upper_threshold > self.threshold:
                raise RPGEventError("range comparison needs ordered upper bound")
            _bounded(self.upper_threshold,"upper bound")
        elif self.upper_threshold is not None:
            raise RPGEventError("upper bound only valid for ranges")

    def evaluate(self, prior: float | None, current: float) -> bool:
        now=_bounded(current,"current sensor")
        past=None if prior is None else _bounded(prior,"prior sensor")
        t=self.threshold
        h=self.hysteresis
        if self.comparison=="above": return now>t+h
        if self.comparison=="below": return now<t-h
        if self.comparison=="at_least": return now>=t+h
        if self.comparison=="at_most": return now<=t-h
        if self.comparison=="cross_up": return (past is not None
                                                   and past<=t-h and now>t+h)
        if self.comparison=="cross_down": return (past is not None
                                                     and past>=t+h and now<t-h)
        assert self.upper_threshold is not None
        if self.comparison=="inside_range":
            return t+h<=now<=self.upper_threshold-h
        return now<t-h or now>self.upper_threshold+h


@dataclass(frozen=True)
class RPGEventAction:
    kind: str
    channel: str
    target: str
    value: str

    def __post_init__(self) -> None:
        if self.kind not in ACTIONS or self.channel not in EVENT_CHANNELS:
            raise RPGEventError("unregistered RPG action/channel")
        if type(self.target) is not str or not self.target or len(self.target)>128:
            raise RPGEventError("action target required")
        if type(self.value) is not str or len(self.value)>1024:
            raise RPGEventError("action parameter too large")


@dataclass(frozen=True)
class RPGEventPage:
    page_id: str
    priority: int
    conditions: tuple[EnvironmentalTrigger, ...]
    actions: tuple[RPGEventAction, ...]
    required_flags: tuple[tuple[str,bool], ...] = ()
    cooldown_ms: int = 0
    enabled: bool = True
    repeat: bool = True

    def __post_init__(self) -> None:
        if not self.page_id or len(self.page_id)>128:
            raise RPGEventError("page ID required")
        if type(self.priority) is not int or not -100 <= self.priority <= 100:
            raise RPGEventError("priority invalid")
        if not 1<=len(self.conditions)<=32 or not 1<=len(self.actions)<=32:
            raise RPGEventError("1..32 conditions and actions required")
        if len(self.required_flags)>64:
            raise RPGEventError("too many flags")
        if any(type(name) is not str or not name or len(name)>128 or type(v) is not bool
               for name,v in self.required_flags):
            raise RPGEventError("invalid event flag predicate")
        if type(self.cooldown_ms) is not int or not 0<=self.cooldown_ms<=86_400_000:
            raise RPGEventError("cooldown out of bounds")
        if type(self.enabled) is not bool or type(self.repeat) is not bool:
            raise RPGEventError("event booleans required")


@dataclass(frozen=True)
class RPGEventDecision:
    page_id: str
    priority: int
    observations: tuple[tuple[str,float], ...]
    actions: tuple[RPGEventAction, ...]
    evidence_digest: str
    authority: str = "proposal_only_no_world_mutation"


@dataclass(frozen=True)
class RPGEventEvaluation:
    accepted: tuple[RPGEventDecision, ...]
    suppressed: tuple[str, ...]
    missing_signals: tuple[str, ...]
    required_runtime_approvals: bool = True


def evaluate_environment_events(
    pages: tuple[RPGEventPage, ...],
    *, current: Mapping[str,float],
    previous: Mapping[str,float] | None = None,
    flags: Mapping[str,bool] | None = None,
    now_ms: int,
    last_fired_ms: Mapping[str,int] | None = None,
    completed_once: frozenset[str] = frozenset(),
) -> RPGEventEvaluation:
    """Deterministically evaluate pages, priority, and target/channel conflicts.

    Observe, filter, and return proposals. Caller owns event dispatch, signoff,
    debouncing state, quest canon and last-fire timestamp persistence.
    """
    if len(pages)>4096 or len({p.page_id for p in pages})!=len(pages):
        raise RPGEventError("page limit or duplicate id")
    if type(now_ms) is not int or not 0<=now_ms<=2**63-1:
        raise RPGEventError("invalid canonical clock")
    if not isinstance(current,Mapping) or (previous is not None and not isinstance(previous,Mapping)):
        raise RPGEventError("observations must be mappings")
    prior=previous or {}
    flags=flags or {}
    fired=last_fired_ms or {}
    if len(current)>256 or len(prior)>256 or len(flags)>4096:
        raise RPGEventError("environment observation budgets exceeded")
    if any(key not in RPG_ENVIRONMENT_SIGNALS for key in (*current,*prior)):
        raise RPGEventError("unknown environmental observation")
    if any(type(v) is not bool for v in flags.values()):
        raise RPGEventError("flag values must be boolean")
    if any(type(t) is not int or t<0 or t>now_ms for t in fired.values()):
        raise RPGEventError("last-fired receipt after clock/invalid")
    proposals=[]
    suppressed=[]
    absent=set()
    reserved=set()
    for page in sorted(pages,key=lambda p:(-p.priority,p.page_id)):
        if not page.enabled or (not page.repeat and page.page_id in completed_once):
            suppressed.append(page.page_id)
            continue
        last=fired.get(page.page_id)
        if last is not None and now_ms-last<page.cooldown_ms:
            suppressed.append(page.page_id)
            continue
        if any(flags.get(name,False)!=expected for name,expected in page.required_flags):
            suppressed.append(page.page_id)
            continue
        observations=[]
        matched=True
        for cond in page.conditions:
            if cond.signal not in current:
                absent.add(cond.signal)
                matched=False
                break
            value=_bounded(current[cond.signal],cond.signal)
            if not cond.evaluate(prior.get(cond.signal),value):
                matched=False
                break
            observations.append((cond.signal,value))
        if not matched:
            suppressed.append(page.page_id)
            continue
        # For non-commutative operations, highest priority on same
        # channel+target wins. Independent targets/channels may run together.
        keys={(a.channel,a.target) for a in page.actions}
        if reserved.intersection(keys):
            suppressed.append(page.page_id)
            continue
        reserved.update(keys)
        receipt=json.dumps([page.page_id,page.priority,observations,
                            [a.__dict__ for a in page.actions]],
                           sort_keys=True,separators=(",",":"),allow_nan=False)
        proposals.append(RPGEventDecision(
            page.page_id,page.priority,tuple(observations),page.actions,
            sha256(receipt.encode()).hexdigest()))
    return RPGEventEvaluation(tuple(proposals),tuple(suppressed),
                              tuple(sorted(absent)))


def event_authoring_catalog() -> dict:
    """Discoverable editor options without exposing execution authority."""
    return {
        "schema":"skeleton.forge.frontier_rpg_events.v1",
        "available_signals":tuple(sorted(RPG_ENVIRONMENT_SIGNALS)),
        "comparisons":tuple(sorted(COMPARISONS)),
        "actions":tuple(sorted(ACTIONS)),
        "channels":tuple(sorted(EVENT_CHANNELS)),
        "authority":"editor_metadata_only",
    }
