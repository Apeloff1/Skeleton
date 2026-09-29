"""Pure energy/stamina policy adapted from Lorebuffa/Openworld.

The two source repositories carry closely related ``backend/energy_routes.py``
implementations. Their framework, MongoDB, wallet, inventory and ad-provider
coupling remain source-owned. This module promotes only the portable policy:
maximum-energy scaling, time-based regeneration, bounded spend/restore,
perfect-catch refunds, daily ad limits and timed booster effects.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be positive")
    return value


def _nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


def _finite_positive(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be finite")
    if numeric <= 0.0:
        raise ValueError(f"{field_name} must be positive")
    return numeric


def _normalized_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if normalized != value:
        raise ValueError(f"{field_name} must be normalized")
    return value


def _aware_utc(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class EnergyPolicy:
    base_max_energy: int = 100
    regen_rate_per_minute: float = 1.0
    level_bonus_per_10_levels: int = 10
    vip_bonus_multiplier: float = 1.5
    perfect_catch_refund: int = 1
    ad_restore: int = 10
    ad_daily_limit: int = 10
    gem_refill_cost: int = 50

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "base_max_energy", _positive_int(self.base_max_energy, "base_max_energy")
        )
        object.__setattr__(
            self,
            "regen_rate_per_minute",
            _finite_positive(self.regen_rate_per_minute, "regen_rate_per_minute"),
        )
        object.__setattr__(
            self,
            "level_bonus_per_10_levels",
            _nonnegative_int(self.level_bonus_per_10_levels, "level_bonus_per_10_levels"),
        )
        object.__setattr__(
            self,
            "vip_bonus_multiplier",
            _finite_positive(self.vip_bonus_multiplier, "vip_bonus_multiplier"),
        )
        object.__setattr__(
            self,
            "perfect_catch_refund",
            _nonnegative_int(self.perfect_catch_refund, "perfect_catch_refund"),
        )
        object.__setattr__(
            self, "ad_restore", _nonnegative_int(self.ad_restore, "ad_restore")
        )
        object.__setattr__(
            self, "ad_daily_limit", _positive_int(self.ad_daily_limit, "ad_daily_limit")
        )
        object.__setattr__(
            self,
            "gem_refill_cost",
            _nonnegative_int(self.gem_refill_cost, "gem_refill_cost"),
        )


DEFAULT_ENERGY_POLICY = EnergyPolicy()


@dataclass(frozen=True, slots=True)
class EnergyState:
    current_energy: int
    max_energy: int
    last_updated: datetime
    infinite_until: datetime | None = None
    regen_multiplier: float = 1.0
    regen_multiplier_until: datetime | None = None
    total_energy_spent: int = 0
    total_energy_restored: int = 0
    ads_watched_today: int = 0
    last_ad_watch: datetime | None = None

    def __post_init__(self) -> None:
        maximum = _positive_int(self.max_energy, "energy max_energy")
        current = _nonnegative_int(self.current_energy, "energy current_energy")
        if current > maximum:
            raise ValueError("energy current_energy must not exceed max_energy")
        object.__setattr__(self, "current_energy", current)
        object.__setattr__(self, "max_energy", maximum)
        object.__setattr__(
            self, "last_updated", _aware_utc(self.last_updated, "energy last_updated")
        )
        if self.infinite_until is not None:
            object.__setattr__(
                self,
                "infinite_until",
                _aware_utc(self.infinite_until, "energy infinite_until"),
            )
        object.__setattr__(
            self,
            "regen_multiplier",
            _finite_positive(self.regen_multiplier, "energy regen_multiplier"),
        )
        if self.regen_multiplier_until is not None:
            object.__setattr__(
                self,
                "regen_multiplier_until",
                _aware_utc(
                    self.regen_multiplier_until,
                    "energy regen_multiplier_until",
                ),
            )
        object.__setattr__(
            self,
            "total_energy_spent",
            _nonnegative_int(self.total_energy_spent, "energy total_energy_spent"),
        )
        object.__setattr__(
            self,
            "total_energy_restored",
            _nonnegative_int(self.total_energy_restored, "energy total_energy_restored"),
        )
        object.__setattr__(
            self,
            "ads_watched_today",
            _nonnegative_int(self.ads_watched_today, "energy ads_watched_today"),
        )
        if self.last_ad_watch is not None:
            object.__setattr__(
                self,
                "last_ad_watch",
                _aware_utc(self.last_ad_watch, "energy last_ad_watch"),
            )


@dataclass(frozen=True, slots=True)
class EnergyBoosterSpec:
    id: str
    name: str
    energy_restore: int = 0
    infinite_duration_minutes: int = 0
    regen_multiplier: float = 1.0
    duration_minutes: int = 0
    cost: Mapping[str, int] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _normalized_text(self.id, "energy booster id"))
        object.__setattr__(self, "name", _normalized_text(self.name, "energy booster name"))
        object.__setattr__(
            self,
            "energy_restore",
            _nonnegative_int(self.energy_restore, "energy booster energy_restore"),
        )
        object.__setattr__(
            self,
            "infinite_duration_minutes",
            _nonnegative_int(
                self.infinite_duration_minutes,
                "energy booster infinite_duration_minutes",
            ),
        )
        object.__setattr__(
            self,
            "regen_multiplier",
            _finite_positive(self.regen_multiplier, "energy booster regen_multiplier"),
        )
        object.__setattr__(
            self,
            "duration_minutes",
            _nonnegative_int(self.duration_minutes, "energy booster duration_minutes"),
        )
        effects = (
            int(self.energy_restore > 0)
            + int(self.infinite_duration_minutes > 0)
            + int(self.regen_multiplier != 1.0)
        )
        if effects != 1:
            raise ValueError("energy booster must define exactly one effect")
        if self.regen_multiplier != 1.0 and self.duration_minutes < 1:
            raise ValueError("regen multiplier booster requires positive duration_minutes")
        raw_cost = self.cost or {}
        normalized_cost: dict[str, int] = {}
        for currency, amount in raw_cost.items():
            key = _normalized_text(currency, "energy booster cost currency")
            if key in normalized_cost:
                raise ValueError(f"duplicate energy booster cost currency: {key}")
            normalized_cost[key] = _nonnegative_int(
                amount, f"energy booster cost {key}"
            )
        object.__setattr__(self, "cost", normalized_cost)


@dataclass(frozen=True, slots=True)
class EnergyStatus:
    state: EnergyState
    is_infinite: bool
    minutes_to_full: int


@dataclass(frozen=True, slots=True)
class AdRestorePlan:
    state: EnergyState
    restored: int
    ads_remaining: int


def energy_booster_from_record(record: Mapping[str, Any]) -> EnergyBoosterSpec:
    if not isinstance(record, Mapping):
        raise TypeError("energy booster record must be a mapping")
    raw_cost = record.get("cost", {})
    if not isinstance(raw_cost, Mapping):
        raise TypeError("energy booster cost must be a mapping")
    return EnergyBoosterSpec(
        id=_normalized_text(record.get("id"), "energy booster id"),
        name=_normalized_text(record.get("name"), "energy booster name"),
        energy_restore=_nonnegative_int(
            record.get("energy_restore", 0), "energy booster energy_restore"
        ),
        infinite_duration_minutes=_nonnegative_int(
            record.get("infinite_duration_minutes", 0),
            "energy booster infinite_duration_minutes",
        ),
        regen_multiplier=_finite_positive(
            record.get("regen_multiplier", 1.0),
            "energy booster regen_multiplier",
        ),
        duration_minutes=_nonnegative_int(
            record.get("duration_minutes", 0),
            "energy booster duration_minutes",
        ),
        cost=dict(raw_cost),
    )


def max_energy_for_level(
    level: int,
    *,
    vip_active: bool = False,
    policy: EnergyPolicy = DEFAULT_ENERGY_POLICY,
) -> int:
    level_value = _positive_int(level, "energy level")
    if not isinstance(vip_active, bool):
        raise TypeError("vip_active must be a boolean")
    level_bonus = (level_value // 10) * policy.level_bonus_per_10_levels
    vip_bonus = (
        int(policy.base_max_energy * (policy.vip_bonus_multiplier - 1.0))
        if vip_active
        else 0
    )
    return policy.base_max_energy + level_bonus + vip_bonus


def initialize_energy(
    *,
    now: datetime,
    level: int = 1,
    vip_active: bool = False,
    policy: EnergyPolicy = DEFAULT_ENERGY_POLICY,
) -> EnergyState:
    current_time = _aware_utc(now, "energy now")
    maximum = max_energy_for_level(level, vip_active=vip_active, policy=policy)
    return EnergyState(
        current_energy=maximum,
        max_energy=maximum,
        last_updated=current_time,
    )


def sync_max_energy(
    state: EnergyState,
    *,
    level: int,
    vip_active: bool = False,
    policy: EnergyPolicy = DEFAULT_ENERGY_POLICY,
) -> EnergyState:
    maximum = max_energy_for_level(level, vip_active=vip_active, policy=policy)
    return replace(
        state,
        max_energy=maximum,
        current_energy=min(state.current_energy, maximum),
    )


def _active_infinite(state: EnergyState, now: datetime) -> bool:
    return state.infinite_until is not None and state.infinite_until > now


def _regenerated_units(
    state: EnergyState,
    now: datetime,
    policy: EnergyPolicy,
) -> int:
    if now < state.last_updated:
        raise ValueError("energy now must not be earlier than last_updated")
    if now == state.last_updated:
        return 0

    start = state.last_updated
    boosted_until = state.regen_multiplier_until
    multiplier = state.regen_multiplier
    units = 0.0

    if boosted_until is not None and boosted_until > start and multiplier != 1.0:
        boosted_end = min(now, boosted_until)
        if boosted_end > start:
            boosted_minutes = (boosted_end - start).total_seconds() / 60.0
            units += boosted_minutes * policy.regen_rate_per_minute * multiplier
            start = boosted_end

    if now > start:
        base_minutes = (now - start).total_seconds() / 60.0
        units += base_minutes * policy.regen_rate_per_minute

    return max(0, int(units))


def regenerate_energy(
    state: EnergyState,
    *,
    now: datetime,
    policy: EnergyPolicy = DEFAULT_ENERGY_POLICY,
) -> EnergyState:
    current_time = _aware_utc(now, "energy now")
    if current_time < state.last_updated:
        raise ValueError("energy now must not be earlier than last_updated")

    infinite_active = _active_infinite(state, current_time)
    infinite_until = state.infinite_until if infinite_active else None

    multiplier_active = (
        state.regen_multiplier_until is not None
        and state.regen_multiplier_until > current_time
        and state.regen_multiplier != 1.0
    )
    next_multiplier = state.regen_multiplier if multiplier_active else 1.0
    next_multiplier_until = state.regen_multiplier_until if multiplier_active else None

    if infinite_active:
        return replace(
            state,
            current_energy=state.max_energy,
            last_updated=current_time,
            infinite_until=infinite_until,
            regen_multiplier=next_multiplier,
            regen_multiplier_until=next_multiplier_until,
        )

    regenerated = _regenerated_units(state, current_time, policy)
    current = min(state.max_energy, state.current_energy + regenerated)
    actual = current - state.current_energy
    return replace(
        state,
        current_energy=current,
        last_updated=current_time,
        infinite_until=None,
        regen_multiplier=next_multiplier,
        regen_multiplier_until=next_multiplier_until,
        total_energy_restored=state.total_energy_restored + actual,
    )


def consume_energy(
    state: EnergyState,
    amount: int,
    *,
    now: datetime,
    policy: EnergyPolicy = DEFAULT_ENERGY_POLICY,
) -> EnergyState:
    requested = _positive_int(amount, "energy spend amount")
    current_time = _aware_utc(now, "energy now")
    prepared = regenerate_energy(state, now=current_time, policy=policy)
    if _active_infinite(prepared, current_time):
        return prepared
    if prepared.current_energy < requested:
        raise ValueError(
            f"not enough energy: have {prepared.current_energy}, need {requested}"
        )
    return replace(
        prepared,
        current_energy=prepared.current_energy - requested,
        last_updated=current_time,
        total_energy_spent=prepared.total_energy_spent + requested,
    )


def restore_energy(
    state: EnergyState,
    amount: int,
    *,
    now: datetime,
    policy: EnergyPolicy = DEFAULT_ENERGY_POLICY,
) -> EnergyState:
    requested = _nonnegative_int(amount, "energy restore amount")
    current_time = _aware_utc(now, "energy now")
    prepared = regenerate_energy(state, now=current_time, policy=policy)
    current = min(prepared.max_energy, prepared.current_energy + requested)
    actual = current - prepared.current_energy
    return replace(
        prepared,
        current_energy=current,
        last_updated=current_time,
        total_energy_restored=prepared.total_energy_restored + actual,
    )


def perfect_catch_refund(
    state: EnergyState,
    *,
    now: datetime,
    policy: EnergyPolicy = DEFAULT_ENERGY_POLICY,
) -> EnergyState:
    return restore_energy(
        state,
        policy.perfect_catch_refund,
        now=now,
        policy=policy,
    )


def apply_booster(
    state: EnergyState,
    booster: EnergyBoosterSpec,
    *,
    now: datetime,
    policy: EnergyPolicy = DEFAULT_ENERGY_POLICY,
) -> EnergyState:
    current_time = _aware_utc(now, "energy now")
    prepared = regenerate_energy(state, now=current_time, policy=policy)

    if booster.energy_restore > 0:
        return restore_energy(
            prepared,
            booster.energy_restore,
            now=current_time,
            policy=policy,
        )

    if booster.infinite_duration_minutes > 0:
        until = current_time + timedelta(minutes=booster.infinite_duration_minutes)
        return replace(
            prepared,
            current_energy=prepared.max_energy,
            last_updated=current_time,
            infinite_until=until,
        )

    until = current_time + timedelta(minutes=booster.duration_minutes)
    return replace(
        prepared,
        last_updated=current_time,
        regen_multiplier=booster.regen_multiplier,
        regen_multiplier_until=until,
    )


def restore_from_ad(
    state: EnergyState,
    *,
    now: datetime,
    policy: EnergyPolicy = DEFAULT_ENERGY_POLICY,
) -> AdRestorePlan:
    current_time = _aware_utc(now, "energy now")
    same_day = (
        state.last_ad_watch is not None
        and state.last_ad_watch.date() == current_time.date()
    )
    watched = state.ads_watched_today if same_day else 0
    if watched >= policy.ad_daily_limit:
        raise ValueError("daily ad energy limit reached")

    prepared = replace(
        state,
        ads_watched_today=watched,
        last_ad_watch=state.last_ad_watch if same_day else None,
    )
    before = regenerate_energy(prepared, now=current_time, policy=policy)
    restored_state = restore_energy(
        before,
        policy.ad_restore,
        now=current_time,
        policy=policy,
    )
    restored = restored_state.current_energy - before.current_energy
    updated = replace(
        restored_state,
        ads_watched_today=watched + 1,
        last_ad_watch=current_time,
    )
    return AdRestorePlan(
        state=updated,
        restored=restored,
        ads_remaining=policy.ad_daily_limit - (watched + 1),
    )


def minutes_to_full(
    state: EnergyState,
    *,
    now: datetime,
    policy: EnergyPolicy = DEFAULT_ENERGY_POLICY,
) -> int:
    current_time = _aware_utc(now, "energy now")
    prepared = regenerate_energy(state, now=current_time, policy=policy)
    if _active_infinite(prepared, current_time) or prepared.current_energy >= prepared.max_energy:
        return 0

    needed = prepared.max_energy - prepared.current_energy
    rate = policy.regen_rate_per_minute
    boost_until = prepared.regen_multiplier_until
    if (
        boost_until is not None
        and boost_until > current_time
        and prepared.regen_multiplier != 1.0
    ):
        boosted_rate = rate * prepared.regen_multiplier
        boosted_minutes = (boost_until - current_time).total_seconds() / 60.0
        boosted_capacity = boosted_minutes * boosted_rate
        if boosted_capacity >= needed:
            return math.ceil(needed / boosted_rate)
        remaining = needed - boosted_capacity
        return math.ceil(boosted_minutes + (remaining / rate))

    return math.ceil(needed / rate)


def energy_status(
    state: EnergyState,
    *,
    now: datetime,
    policy: EnergyPolicy = DEFAULT_ENERGY_POLICY,
) -> EnergyStatus:
    current_time = _aware_utc(now, "energy now")
    prepared = regenerate_energy(state, now=current_time, policy=policy)
    return EnergyStatus(
        state=prepared,
        is_infinite=_active_infinite(prepared, current_time),
        minutes_to_full=minutes_to_full(prepared, now=current_time, policy=policy),
    )
