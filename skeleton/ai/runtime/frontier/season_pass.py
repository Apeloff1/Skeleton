"""Dependency-free season-pass policy promoted from Lorebuffa/Openworld.

Both source repositories carry the exact same ``backend/rewards_routes.py``
blob ``27df9034118b9c5960668a231aed6d75385f8a9e``. Daily streak semantics are
already canonical in :mod:`skeleton.frontier.achievements`; this module promotes
only the still-missing season-pass tier, XP, entitlement and claim policy.

Database access, IAP/payment processing and wallet/inventory mutation remain
outside the frontier kernel. Premium activation therefore requires an explicit
verified-entitlement input instead of preserving the source's simulated purchase
shortcut.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Mapping, Sequence


_ALLOWED_REWARD_TYPES = frozenset(
    {
        "coins",
        "gems",
        "bait",
        "mystery_box",
        "exclusive_cosmetic",
        "legendary_rod",
    }
)


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value or value.strip() != value:
        raise ValueError(f"{field_name} must be non-empty and normalized")
    return value


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


def _claimed_levels(values: Sequence[int] | frozenset[int], field_name: str) -> frozenset[int]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} must be a sequence of integers")
    claimed: set[int] = set()
    for raw_value in values:
        level = _positive_int(raw_value, f"{field_name} level")
        if level in claimed:
            raise ValueError(f"duplicate {field_name} level: {level}")
        claimed.add(level)
    return frozenset(claimed)


@dataclass(frozen=True, slots=True)
class SeasonReward:
    type: str
    amount: int = 1
    item_id: str | None = None
    exclusive: bool = False

    def __post_init__(self) -> None:
        reward_type = _text(self.type, "season reward type")
        if reward_type not in _ALLOWED_REWARD_TYPES:
            raise ValueError(f"unsupported season reward type: {reward_type}")
        object.__setattr__(self, "type", reward_type)
        object.__setattr__(self, "amount", _positive_int(self.amount, "season reward amount"))
        if self.item_id is not None:
            object.__setattr__(self, "item_id", _text(self.item_id, "season reward item_id"))
        if not isinstance(self.exclusive, bool):
            raise TypeError("season reward exclusive must be a boolean")
        if reward_type in {"exclusive_cosmetic", "legendary_rod"} and self.item_id is None:
            raise ValueError(f"{reward_type} reward requires item_id")
        if reward_type not in {"exclusive_cosmetic", "legendary_rod"} and self.item_id is not None:
            raise ValueError(f"{reward_type} reward must not carry item_id")


@dataclass(frozen=True, slots=True)
class SeasonTier:
    level: int
    required_xp: int
    free_reward: SeasonReward | None
    premium_reward: SeasonReward | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "level", _positive_int(self.level, "season tier level"))
        object.__setattr__(
            self,
            "required_xp",
            _positive_int(self.required_xp, "season tier required_xp"),
        )
        if self.free_reward is not None and not isinstance(self.free_reward, SeasonReward):
            raise TypeError("season tier free_reward must be SeasonReward or None")
        if self.premium_reward is not None and not isinstance(self.premium_reward, SeasonReward):
            raise TypeError("season tier premium_reward must be SeasonReward or None")


@dataclass(frozen=True, slots=True)
class SeasonPassSpec:
    id: str
    tiers: tuple[SeasonTier, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _text(self.id, "season pass id"))
        if not isinstance(self.tiers, tuple):
            object.__setattr__(self, "tiers", tuple(self.tiers))
        if not self.tiers:
            raise ValueError("season pass must contain at least one tier")
        expected_level = 1
        for tier in self.tiers:
            if not isinstance(tier, SeasonTier):
                raise TypeError("season pass tiers must contain SeasonTier values")
            if tier.level != expected_level:
                raise ValueError("season pass tier levels must be contiguous and start at 1")
            expected_level += 1

    @property
    def max_level(self) -> int:
        return len(self.tiers)

    def tier(self, level: int) -> SeasonTier:
        numeric = _positive_int(level, "season tier level")
        if numeric > self.max_level:
            raise ValueError("season tier level exceeds season pass max_level")
        return self.tiers[numeric - 1]


@dataclass(frozen=True, slots=True)
class SeasonProgress:
    season_pass_id: str
    current_level: int = 1
    current_xp: int = 0
    is_premium: bool = False
    claimed_free_rewards: frozenset[int] = frozenset()
    claimed_premium_rewards: frozenset[int] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "season_pass_id",
            _text(self.season_pass_id, "season progress season_pass_id"),
        )
        level = _positive_int(self.current_level, "season progress current_level")
        object.__setattr__(self, "current_level", level)
        object.__setattr__(
            self,
            "current_xp",
            _nonnegative_int(self.current_xp, "season progress current_xp"),
        )
        if not isinstance(self.is_premium, bool):
            raise TypeError("season progress is_premium must be a boolean")
        free_claimed = _claimed_levels(
            self.claimed_free_rewards, "claimed free season reward"
        )
        premium_claimed = _claimed_levels(
            self.claimed_premium_rewards, "claimed premium season reward"
        )
        if any(claimed > level for claimed in free_claimed | premium_claimed):
            raise ValueError("claimed season reward level cannot exceed current_level")
        if premium_claimed and not self.is_premium:
            raise ValueError("premium reward claims require premium entitlement")
        object.__setattr__(self, "claimed_free_rewards", free_claimed)
        object.__setattr__(self, "claimed_premium_rewards", premium_claimed)


@dataclass(frozen=True, slots=True)
class SeasonXPPlan:
    progress: SeasonProgress
    requested_xp: int
    applied_xp: int
    levels_gained: int


@dataclass(frozen=True, slots=True)
class SeasonRewardPlan:
    progress: SeasonProgress
    level: int
    premium: bool
    reward: SeasonReward
    currency_increments: Mapping[str, int]
    inventory_increments: Mapping[str, int]
    unlock_items: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "currency_increments", MappingProxyType(dict(self.currency_increments)))
        object.__setattr__(self, "inventory_increments", MappingProxyType(dict(self.inventory_increments)))


def generate_default_season_tiers(max_level: int = 50) -> tuple[SeasonTier, ...]:
    """Generate the exact shared-source season tier schedule as pure data."""

    maximum = _positive_int(max_level, "season pass max_level")
    tiers: list[SeasonTier] = []
    for level in range(1, maximum + 1):
        required_xp = level * 100 + (level - 1) * 50
        if level % 5 == 0:
            free_reward = SeasonReward("mystery_box")
        elif level % 3 == 0:
            free_reward = SeasonReward("bait", amount=5)
        else:
            free_reward = SeasonReward("coins", amount=level * 50)

        if level == maximum:
            premium_reward = SeasonReward(
                "legendary_rod",
                item_id="season_rod",
                exclusive=True,
            )
        elif level % 10 == 0:
            premium_reward = SeasonReward(
                "exclusive_cosmetic",
                item_id=f"season_cosmetic_{level}",
            )
        elif level % 5 == 0:
            premium_reward = SeasonReward("gems", amount=50 + level)
        else:
            premium_reward = SeasonReward("coins", amount=level * 100)

        tiers.append(
            SeasonTier(
                level=level,
                required_xp=required_xp,
                free_reward=free_reward,
                premium_reward=premium_reward,
            )
        )
    return tuple(tiers)


def default_season_pass(season_pass_id: str, *, max_level: int = 50) -> SeasonPassSpec:
    return SeasonPassSpec(
        id=season_pass_id,
        tiers=generate_default_season_tiers(max_level),
    )


def initial_season_progress(spec: SeasonPassSpec) -> SeasonProgress:
    if not isinstance(spec, SeasonPassSpec):
        raise TypeError("spec must be SeasonPassSpec")
    return SeasonProgress(season_pass_id=spec.id)


def _validated_progress(spec: SeasonPassSpec, progress: SeasonProgress) -> SeasonProgress:
    if not isinstance(spec, SeasonPassSpec):
        raise TypeError("spec must be SeasonPassSpec")
    if not isinstance(progress, SeasonProgress):
        raise TypeError("progress must be SeasonProgress")
    if progress.season_pass_id != spec.id:
        raise ValueError("season progress does not belong to supplied season pass")
    if progress.current_level > spec.max_level:
        raise ValueError("season progress current_level exceeds season pass max_level")
    if progress.current_level < spec.max_level:
        threshold = spec.tier(progress.current_level).required_xp
        if progress.current_xp >= threshold:
            raise ValueError("season progress XP must be normalized below current tier threshold")
    return progress


def xp_to_next_level(spec: SeasonPassSpec, progress: SeasonProgress) -> int:
    progress = _validated_progress(spec, progress)
    if progress.current_level >= spec.max_level:
        return 0
    return spec.tier(progress.current_level).required_xp - progress.current_xp


def add_season_xp(
    spec: SeasonPassSpec,
    progress: SeasonProgress,
    xp_amount: int,
) -> SeasonXPPlan:
    """Apply XP and drain every crossed tier threshold in one transition."""

    progress = _validated_progress(spec, progress)
    requested = _nonnegative_int(xp_amount, "season XP amount")
    if progress.current_level >= spec.max_level or requested == 0:
        return SeasonXPPlan(progress, requested, 0, 0)

    new_xp = progress.current_xp + requested
    new_level = progress.current_level
    levels_gained = 0
    while new_level < spec.max_level:
        threshold = spec.tier(new_level).required_xp
        if new_xp < threshold:
            break
        new_xp -= threshold
        new_level += 1
        levels_gained += 1

    next_progress = replace(progress, current_level=new_level, current_xp=new_xp)
    return SeasonXPPlan(next_progress, requested, requested, levels_gained)


def activate_premium(
    spec: SeasonPassSpec,
    progress: SeasonProgress,
    *,
    entitlement_verified: bool,
) -> SeasonProgress:
    """Activate premium only after an external payment/entitlement boundary verifies it."""

    progress = _validated_progress(spec, progress)
    if not isinstance(entitlement_verified, bool):
        raise TypeError("entitlement_verified must be a boolean")
    if not entitlement_verified:
        raise PermissionError("premium season pass requires verified entitlement")
    if progress.is_premium:
        return progress
    return replace(progress, is_premium=True)


def _reward_plan(
    progress: SeasonProgress,
    *,
    level: int,
    premium: bool,
    reward: SeasonReward,
) -> SeasonRewardPlan:
    currency: dict[str, int] = {}
    inventory: dict[str, int] = {}
    unlock_items: tuple[str, ...] = ()
    if reward.type in {"coins", "gems"}:
        currency[reward.type] = reward.amount
    elif reward.type in {"bait", "mystery_box"}:
        inventory[reward.type] = reward.amount
    elif reward.type in {"exclusive_cosmetic", "legendary_rod"}:
        assert reward.item_id is not None
        unlock_items = (reward.item_id,)
    return SeasonRewardPlan(
        progress=progress,
        level=level,
        premium=premium,
        reward=reward,
        currency_increments=currency,
        inventory_increments=inventory,
        unlock_items=unlock_items,
    )


def claim_season_reward(
    spec: SeasonPassSpec,
    progress: SeasonProgress,
    *,
    level: int,
    premium: bool = False,
) -> SeasonRewardPlan:
    """Plan an idempotent tier claim without mutating wallets or inventories."""

    progress = _validated_progress(spec, progress)
    numeric_level = _positive_int(level, "season reward level")
    if numeric_level > progress.current_level:
        raise PermissionError("season reward level has not been reached")
    if numeric_level > spec.max_level:
        raise ValueError("season reward level exceeds season pass max_level")
    if not isinstance(premium, bool):
        raise TypeError("premium must be a boolean")
    if premium and not progress.is_premium:
        raise PermissionError("premium season pass required")

    tier = spec.tier(numeric_level)
    reward = tier.premium_reward if premium else tier.free_reward
    if reward is None:
        raise ValueError("season tier has no reward on requested track")

    if premium:
        if numeric_level in progress.claimed_premium_rewards:
            raise ValueError("premium season reward already claimed")
        claimed = set(progress.claimed_premium_rewards)
        claimed.add(numeric_level)
        next_progress = replace(progress, claimed_premium_rewards=frozenset(claimed))
    else:
        if numeric_level in progress.claimed_free_rewards:
            raise ValueError("free season reward already claimed")
        claimed = set(progress.claimed_free_rewards)
        claimed.add(numeric_level)
        next_progress = replace(progress, claimed_free_rewards=frozenset(claimed))

    return _reward_plan(
        next_progress,
        level=numeric_level,
        premium=premium,
        reward=reward,
    )
