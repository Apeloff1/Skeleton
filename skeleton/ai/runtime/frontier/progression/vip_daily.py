"""Pure VIP daily challenge and point-reward policy.

Promoted from the exact shared Lorebuffa/Openworld ``vip_daily_routes.py`` blob
``3d23e083f91053d9df6450043fc12bad7829aa51``.  Persistence, HTTP routing,
source catalogs and wallet mutation remain outside the frontier kernel.

The source challenge claim path marks a Catch-of-the-Day as claimed but does not
check that flag before awarding the same reward again.  This module makes claim
state explicit and single-use.  It also replaces substring fish-name matching and
process-global RNG mutation with exact canonical fish IDs and isolated deterministic
randomness.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from random import Random
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence
import hashlib


_DIFFICULTY_ORDER = ("easy", "medium", "hard", "legendary")


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value or value.strip() != value:
        raise ValueError(f"{field_name} must be non-empty and normalized")
    return value


def _token(value: object, field_name: str) -> str:
    value = _text(value, field_name)
    lowered = value.lower()
    if lowered != value:
        raise ValueError(f"{field_name} must be lowercase and normalized")
    return lowered


def _nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


def _positive_int(value: object, field_name: str) -> int:
    value = _nonnegative_int(value, field_name)
    if value < 1:
        raise ValueError(f"{field_name} must be positive")
    return value


def _positive_map(values: Mapping[str, int], field_name: str) -> Mapping[str, int]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    normalized: dict[str, int] = {}
    for raw_key, raw_value in values.items():
        key = _token(raw_key, f"{field_name} key")
        normalized[key] = _positive_int(raw_value, f"{field_name}[{key!r}]")
    return MappingProxyType(normalized)


def _id_tuple(values: Iterable[str], field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} must be an iterable")
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _token(raw, f"{field_name} entry")
        if value in seen:
            raise ValueError(f"duplicate {field_name} entry: {value}")
        seen.add(value)
        result.append(value)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class CatchPool:
    difficulty: str
    fish_ids: tuple[str, ...]
    min_count: int
    max_count: int
    vip_points: int
    bonus_multiplier_bps: int

    def __post_init__(self) -> None:
        difficulty = _token(self.difficulty, "catch pool difficulty")
        if difficulty not in _DIFFICULTY_ORDER:
            raise ValueError(f"unsupported catch difficulty: {difficulty}")
        fish_ids = _id_tuple(self.fish_ids, "catch pool fish_ids")
        if not fish_ids:
            raise ValueError("catch pool fish_ids must not be empty")
        minimum = _positive_int(self.min_count, "catch pool min_count")
        maximum = _positive_int(self.max_count, "catch pool max_count")
        if maximum < minimum:
            raise ValueError("catch pool max_count must be >= min_count")
        points = _positive_int(self.vip_points, "catch pool vip_points")
        bps = _positive_int(self.bonus_multiplier_bps, "catch pool bonus_multiplier_bps")
        object.__setattr__(self, "difficulty", difficulty)
        object.__setattr__(self, "fish_ids", fish_ids)
        object.__setattr__(self, "min_count", minimum)
        object.__setattr__(self, "max_count", maximum)
        object.__setattr__(self, "vip_points", points)
        object.__setattr__(self, "bonus_multiplier_bps", bps)


@dataclass(frozen=True, slots=True)
class CatchOfDay:
    subject_id: str
    challenge_date: date
    difficulty: str
    target_fish_id: str
    target_count: int
    vip_points: int
    bonus_multiplier_bps: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "subject_id", _text(self.subject_id, "catch subject_id"))
        if not isinstance(self.challenge_date, date):
            raise TypeError("challenge_date must be a date")
        difficulty = _token(self.difficulty, "catch difficulty")
        if difficulty not in _DIFFICULTY_ORDER:
            raise ValueError(f"unsupported catch difficulty: {difficulty}")
        object.__setattr__(self, "difficulty", difficulty)
        object.__setattr__(self, "target_fish_id", _token(self.target_fish_id, "target fish id"))
        object.__setattr__(self, "target_count", _positive_int(self.target_count, "target_count"))
        object.__setattr__(self, "vip_points", _positive_int(self.vip_points, "vip_points"))
        object.__setattr__(
            self,
            "bonus_multiplier_bps",
            _positive_int(self.bonus_multiplier_bps, "bonus_multiplier_bps"),
        )


@dataclass(frozen=True, slots=True)
class CatchOfDayState:
    challenge: CatchOfDay
    progress: int = 0
    completed: bool = False
    claimed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.challenge, CatchOfDay):
            raise TypeError("challenge must be CatchOfDay")
        progress = _nonnegative_int(self.progress, "catch progress")
        if progress > self.challenge.target_count:
            raise ValueError("catch progress may not exceed target_count")
        if not isinstance(self.completed, bool) or not isinstance(self.claimed, bool):
            raise TypeError("catch completed/claimed must be booleans")
        if self.completed != (progress >= self.challenge.target_count):
            raise ValueError("catch completed flag must match progress")
        if self.claimed and not self.completed:
            raise ValueError("catch reward cannot be claimed before completion")
        object.__setattr__(self, "progress", progress)


@dataclass(frozen=True, slots=True)
class CatchRewardPlan:
    state: CatchOfDayState
    vip_points: int
    bonus_coins: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "vip_points", _positive_int(self.vip_points, "catch reward vip_points"))
        object.__setattr__(self, "bonus_coins", _positive_int(self.bonus_coins, "catch reward bonus_coins"))


def source_default_catch_pools() -> tuple[CatchPool, ...]:
    return (
        CatchPool("easy", ("bluegill", "perch", "bass", "catfish", "trout"), 3, 5, 25, 10_000),
        CatchPool("medium", ("pike", "walleye", "salmon", "redfish", "snook"), 2, 3, 50, 12_500),
        CatchPool("hard", ("tarpon", "marlin", "tuna", "sturgeon", "muskie"), 1, 2, 100, 15_000),
        CatchPool("legendary", ("golden_koi", "leviathan", "coelacanth", "sawfish"), 1, 1, 250, 20_000),
    )


def _eligible_difficulties(level: int) -> tuple[str, ...]:
    player_level = _positive_int(level, "player level")
    if player_level >= 60:
        return _DIFFICULTY_ORDER
    if player_level >= 40:
        return _DIFFICULTY_ORDER[:3]
    if player_level >= 20:
        return _DIFFICULTY_ORDER[:2]
    return _DIFFICULTY_ORDER[:1]


def generate_catch_of_day(
    subject_id: str,
    challenge_date: date,
    *,
    player_level: int,
    pools: Sequence[CatchPool] | None = None,
) -> CatchOfDayState:
    subject = _text(subject_id, "catch subject_id")
    if not isinstance(challenge_date, date):
        raise TypeError("challenge_date must be a date")
    catalog = tuple(pools or source_default_catch_pools())
    by_difficulty: dict[str, CatchPool] = {}
    for pool in catalog:
        if not isinstance(pool, CatchPool):
            raise TypeError("pools must contain CatchPool values")
        if pool.difficulty in by_difficulty:
            raise ValueError(f"duplicate catch pool: {pool.difficulty}")
        by_difficulty[pool.difficulty] = pool
    eligible = tuple(
        difficulty
        for difficulty in _eligible_difficulties(player_level)
        if difficulty in by_difficulty
    )
    if not eligible:
        raise ValueError("no eligible catch pool exists")
    seed_material = f"{subject}\0{challenge_date.isoformat()}".encode()
    rng = Random(int.from_bytes(hashlib.sha256(seed_material).digest()[:16], "big"))
    difficulty = rng.choice(eligible)
    pool = by_difficulty[difficulty]
    challenge = CatchOfDay(
        subject_id=subject,
        challenge_date=challenge_date,
        difficulty=difficulty,
        target_fish_id=rng.choice(pool.fish_ids),
        target_count=rng.randint(pool.min_count, pool.max_count),
        vip_points=pool.vip_points,
        bonus_multiplier_bps=pool.bonus_multiplier_bps,
    )
    return CatchOfDayState(challenge=challenge)


def record_catch(
    state: CatchOfDayState,
    *,
    subject_id: str,
    fish_id: str,
    catch_date: date,
) -> CatchOfDayState:
    if not isinstance(state, CatchOfDayState):
        raise TypeError("state must be CatchOfDayState")
    subject = _text(subject_id, "catch subject_id")
    fish = _token(fish_id, "caught fish id")
    if not isinstance(catch_date, date):
        raise TypeError("catch_date must be a date")
    challenge = state.challenge
    if challenge.subject_id != subject:
        raise PermissionError("catch challenge belongs to another subject")
    if challenge.challenge_date != catch_date:
        raise ValueError("catch challenge is not active on this date")
    if state.claimed or state.completed:
        return state
    if fish != challenge.target_fish_id:
        return state
    progress = min(challenge.target_count, state.progress + 1)
    return CatchOfDayState(
        challenge=challenge,
        progress=progress,
        completed=progress >= challenge.target_count,
    )


def claim_catch_reward(
    state: CatchOfDayState,
    *,
    subject_id: str,
    claim_date: date,
    vip_tier: int,
) -> CatchRewardPlan:
    if not isinstance(state, CatchOfDayState):
        raise TypeError("state must be CatchOfDayState")
    subject = _text(subject_id, "catch subject_id")
    tier = _positive_int(vip_tier, "VIP tier")
    if tier > 4:
        raise ValueError("VIP tier must not exceed 4")
    challenge = state.challenge
    if challenge.subject_id != subject:
        raise PermissionError("catch challenge belongs to another subject")
    if challenge.challenge_date != claim_date:
        raise ValueError("catch challenge has expired")
    if not state.completed:
        raise ValueError("catch challenge is not completed")
    if state.claimed:
        raise ValueError("catch challenge reward already claimed")
    tier_multiplier_bps = 10_000 + tier * 1_000
    points = challenge.vip_points * tier_multiplier_bps * challenge.bonus_multiplier_bps // 100_000_000
    coins = 500 * challenge.bonus_multiplier_bps // 10_000
    return CatchRewardPlan(
        state=replace(state, claimed=True),
        vip_points=max(1, points),
        bonus_coins=max(1, coins),
    )


@dataclass(frozen=True, slots=True)
class VIPPointState:
    available_points: int = 0
    lifetime_points: int = 0
    claimed_milestones: frozenset[int] = frozenset()

    def __post_init__(self) -> None:
        available = _nonnegative_int(self.available_points, "VIP available_points")
        lifetime = _nonnegative_int(self.lifetime_points, "VIP lifetime_points")
        if lifetime < available:
            raise ValueError("VIP lifetime_points must be >= available_points")
        if isinstance(self.claimed_milestones, (str, bytes)):
            raise TypeError("claimed_milestones must be an iterable")
        claimed = frozenset(
            _positive_int(value, "VIP claimed milestone") for value in self.claimed_milestones
        )
        object.__setattr__(self, "available_points", available)
        object.__setattr__(self, "lifetime_points", lifetime)
        object.__setattr__(self, "claimed_milestones", claimed)


def award_vip_points(state: VIPPointState, amount: int) -> VIPPointState:
    if not isinstance(state, VIPPointState):
        raise TypeError("state must be VIPPointState")
    points = _positive_int(amount, "VIP point award")
    return VIPPointState(
        available_points=state.available_points + points,
        lifetime_points=state.lifetime_points + points,
        claimed_milestones=state.claimed_milestones,
    )


@dataclass(frozen=True, slots=True)
class VIPMilestoneSpec:
    milestone: int
    increments: Mapping[str, int]
    energy_refills: int = 0
    vip_days: int = 0
    item_grants: tuple[str, ...] = ()
    title_grants: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "milestone", _positive_int(self.milestone, "VIP milestone"))
        object.__setattr__(self, "increments", _positive_map(self.increments, "VIP milestone increments"))
        object.__setattr__(self, "energy_refills", _nonnegative_int(self.energy_refills, "energy_refills"))
        object.__setattr__(self, "vip_days", _nonnegative_int(self.vip_days, "vip_days"))
        object.__setattr__(self, "item_grants", _id_tuple(self.item_grants, "VIP milestone item_grants"))
        if isinstance(self.title_grants, (str, bytes)):
            raise TypeError("VIP title_grants must be an iterable")
        titles: list[str] = []
        for title in self.title_grants:
            normalized = _text(title, "VIP milestone title")
            if normalized in titles:
                raise ValueError(f"duplicate VIP milestone title: {normalized}")
            titles.append(normalized)
        object.__setattr__(self, "title_grants", tuple(titles))


@dataclass(frozen=True, slots=True)
class VIPMilestoneClaimPlan:
    state: VIPPointState
    reward: VIPMilestoneSpec


def claim_vip_milestone(
    state: VIPPointState,
    reward: VIPMilestoneSpec,
) -> VIPMilestoneClaimPlan:
    """Claim a cumulative milestone once without consuming accumulated points."""

    if not isinstance(state, VIPPointState):
        raise TypeError("state must be VIPPointState")
    if not isinstance(reward, VIPMilestoneSpec):
        raise TypeError("reward must be VIPMilestoneSpec")
    if state.available_points < reward.milestone:
        raise PermissionError("not enough VIP points for milestone")
    if reward.milestone in state.claimed_milestones:
        raise ValueError("VIP milestone already claimed")
    claimed = set(state.claimed_milestones)
    claimed.add(reward.milestone)
    return VIPMilestoneClaimPlan(
        state=VIPPointState(
            available_points=state.available_points,
            lifetime_points=state.lifetime_points,
            claimed_milestones=frozenset(claimed),
        ),
        reward=reward,
    )


def source_default_milestones() -> tuple[VIPMilestoneSpec, ...]:
    return (
        VIPMilestoneSpec(100, {"coins": 1_000, "gems": 5}),
        VIPMilestoneSpec(250, {"coins": 2_500, "gems": 10}, energy_refills=1),
        VIPMilestoneSpec(500, {"coins": 5_000, "gems": 25}, item_grants=("mystery_box",)),
        VIPMilestoneSpec(1_000, {"coins": 10_000, "gems": 50}, vip_days=3),
        VIPMilestoneSpec(2_500, {"coins": 25_000, "gems": 100}, item_grants=("vip_master_rod",)),
        VIPMilestoneSpec(
            5_000,
            {"coins": 50_000, "gems": 250},
            item_grants=("golden_vip_lure",),
            title_grants=("VIP Legend",),
        ),
    )
