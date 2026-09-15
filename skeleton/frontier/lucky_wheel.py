"""Pure lucky-wheel selection and spin-budget policy from shared rewards lineage.

The source lives in the same byte-identical Lorebuffa/Openworld
``backend/rewards_routes.py`` blob as the promoted season pass. Randomness is an
injected draw, not a global RNG dependency. Wallet/inventory mutation and ad
verification stay outside this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Mapping, Sequence


_ALLOWED_SPIN_TYPES = frozenset({"free", "ad", "gem"})
_ALLOWED_REWARD_TYPES = frozenset({"coins", "energy", "bait", "gems", "mystery_box", "legendary_box"})
_ALLOWED_RARITIES = frozenset({"common", "uncommon", "rare", "epic", "legendary"})
_PROBABILITY_EPSILON = 1e-12


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value or value.strip() != value:
        raise ValueError(f"{field_name} must be non-empty and normalized")
    return value


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


def _probability(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    numeric = float(value)
    if not isfinite(numeric):
        raise ValueError(f"{field_name} must be finite")
    if numeric <= 0.0 or numeric > 1.0:
        raise ValueError(f"{field_name} must be in (0, 1]")
    return numeric


@dataclass(frozen=True, slots=True)
class WheelSlot:
    slot_id: int
    reward_type: str
    amount: int
    probability: float
    rarity: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "slot_id", _nonnegative_int(self.slot_id, "wheel slot_id"))
        reward_type = _text(self.reward_type, "wheel reward_type")
        if reward_type not in _ALLOWED_REWARD_TYPES:
            raise ValueError(f"unsupported wheel reward_type: {reward_type}")
        object.__setattr__(self, "reward_type", reward_type)
        object.__setattr__(self, "amount", _positive_int(self.amount, "wheel reward amount"))
        object.__setattr__(
            self,
            "probability",
            _probability(self.probability, "wheel slot probability"),
        )
        rarity = _text(self.rarity, "wheel rarity")
        if rarity not in _ALLOWED_RARITIES:
            raise ValueError(f"unsupported wheel rarity: {rarity}")
        object.__setattr__(self, "rarity", rarity)


@dataclass(frozen=True, slots=True)
class WheelConfig:
    id: str
    slots: tuple[WheelSlot, ...]
    free_spins_per_day: int = 1
    ad_spins_per_day: int = 3
    gem_spin_cost: int = 50

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "wheel id"))
        if not isinstance(self.slots, tuple):
            object.__setattr__(self, "slots", tuple(self.slots))
        if not self.slots:
            raise ValueError("wheel must contain at least one slot")
        slot_ids: set[int] = set()
        total_probability = 0.0
        for slot in self.slots:
            if not isinstance(slot, WheelSlot):
                raise TypeError("wheel slots must contain WheelSlot values")
            if slot.slot_id in slot_ids:
                raise ValueError(f"duplicate wheel slot_id: {slot.slot_id}")
            slot_ids.add(slot.slot_id)
            total_probability += slot.probability
        if abs(total_probability - 1.0) > _PROBABILITY_EPSILON:
            raise ValueError("wheel slot probabilities must sum to 1")
        object.__setattr__(
            self,
            "free_spins_per_day",
            _nonnegative_int(self.free_spins_per_day, "free_spins_per_day"),
        )
        object.__setattr__(
            self,
            "ad_spins_per_day",
            _nonnegative_int(self.ad_spins_per_day, "ad_spins_per_day"),
        )
        object.__setattr__(self, "gem_spin_cost", _positive_int(self.gem_spin_cost, "gem_spin_cost"))


@dataclass(frozen=True, slots=True)
class WheelBudget:
    free_spins_remaining: int
    ad_spins_remaining: int
    total_spins: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "free_spins_remaining",
            _nonnegative_int(self.free_spins_remaining, "free_spins_remaining"),
        )
        object.__setattr__(
            self,
            "ad_spins_remaining",
            _nonnegative_int(self.ad_spins_remaining, "ad_spins_remaining"),
        )
        object.__setattr__(self, "total_spins", _nonnegative_int(self.total_spins, "total_spins"))


@dataclass(frozen=True, slots=True)
class WheelRewardPlan:
    currency_increments: Mapping[str, int]
    inventory_increments: Mapping[str, int]
    energy_increment: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency_increments", MappingProxyType(dict(self.currency_increments)))
        object.__setattr__(self, "inventory_increments", MappingProxyType(dict(self.inventory_increments)))
        object.__setattr__(self, "energy_increment", _nonnegative_int(self.energy_increment, "wheel energy increment"))


@dataclass(frozen=True, slots=True)
class WheelSpinPlan:
    slot: WheelSlot
    budget: WheelBudget
    spin_type: str
    gem_debit: int
    reward: WheelRewardPlan


def default_wheel_config() -> WheelConfig:
    """Return the exact shared-source daily-wheel weights and budgets."""

    return WheelConfig(
        id="daily_wheel",
        slots=(
            WheelSlot(0, "coins", 50, 0.25, "common"),
            WheelSlot(1, "coins", 100, 0.20, "common"),
            WheelSlot(2, "coins", 200, 0.15, "uncommon"),
            WheelSlot(3, "energy", 20, 0.15, "uncommon"),
            WheelSlot(4, "bait", 5, 0.10, "rare"),
            WheelSlot(5, "gems", 10, 0.08, "rare"),
            WheelSlot(6, "gems", 25, 0.04, "epic"),
            WheelSlot(7, "mystery_box", 1, 0.02, "epic"),
            WheelSlot(8, "legendary_box", 1, 0.01, "legendary"),
        ),
        free_spins_per_day=1,
        ad_spins_per_day=3,
        gem_spin_cost=50,
    )


def initial_wheel_budget(config: WheelConfig) -> WheelBudget:
    if not isinstance(config, WheelConfig):
        raise TypeError("config must be WheelConfig")
    return WheelBudget(config.free_spins_per_day, config.ad_spins_per_day)


def select_wheel_slot(config: WheelConfig, draw: float) -> WheelSlot:
    """Select a slot from an injected draw in the half-open interval [0, 1)."""

    if not isinstance(config, WheelConfig):
        raise TypeError("config must be WheelConfig")
    if isinstance(draw, bool) or not isinstance(draw, (int, float)):
        raise TypeError("wheel draw must be numeric")
    numeric = float(draw)
    if not isfinite(numeric) or numeric < 0.0 or numeric >= 1.0:
        raise ValueError("wheel draw must be finite and in [0, 1)")
    cumulative = 0.0
    for slot in config.slots:
        cumulative += slot.probability
        if numeric < cumulative:
            return slot
    # Config validation binds mass to one; reaching this branch implies numeric
    # instability outside the accepted epsilon, so fail closed rather than
    # silently falling back to slot zero as the source does.
    raise RuntimeError("wheel probability traversal did not resolve a slot")


def _reward_plan(slot: WheelSlot) -> WheelRewardPlan:
    if slot.reward_type in {"coins", "gems"}:
        return WheelRewardPlan({slot.reward_type: slot.amount}, {})
    if slot.reward_type == "energy":
        return WheelRewardPlan({}, {}, energy_increment=slot.amount)
    return WheelRewardPlan({}, {slot.reward_type: slot.amount})


def spin_wheel(
    config: WheelConfig,
    budget: WheelBudget,
    *,
    spin_type: str,
    draw: float,
    gem_balance: int = 0,
    ad_verified: bool = False,
) -> WheelSpinPlan:
    """Authorize one spin, select deterministically, and return pure debit/reward plans."""

    if not isinstance(config, WheelConfig):
        raise TypeError("config must be WheelConfig")
    if not isinstance(budget, WheelBudget):
        raise TypeError("budget must be WheelBudget")
    kind = _text(spin_type, "wheel spin_type")
    if kind not in _ALLOWED_SPIN_TYPES:
        raise ValueError(f"unsupported wheel spin_type: {kind}")
    balance = _nonnegative_int(gem_balance, "wheel gem_balance")
    if not isinstance(ad_verified, bool):
        raise TypeError("ad_verified must be a boolean")

    free = budget.free_spins_remaining
    ads = budget.ad_spins_remaining
    gem_debit = 0
    if kind == "free":
        if free < 1:
            raise PermissionError("no free wheel spins remaining")
        free -= 1
    elif kind == "ad":
        if not ad_verified:
            raise PermissionError("ad wheel spin requires verified ad completion")
        if ads < 1:
            raise PermissionError("no ad wheel spins remaining")
        ads -= 1
    else:
        if balance < config.gem_spin_cost:
            raise PermissionError("insufficient gems for wheel spin")
        gem_debit = config.gem_spin_cost

    slot = select_wheel_slot(config, draw)
    next_budget = WheelBudget(free, ads, budget.total_spins + 1)
    return WheelSpinPlan(
        slot=slot,
        budget=next_budget,
        spin_type=kind,
        gem_debit=gem_debit,
        reward=_reward_plan(slot),
    )
