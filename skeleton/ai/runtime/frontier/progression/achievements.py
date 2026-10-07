"""Pure achievement/progression policy from shared Lorebuffa/Openworld lineage.

Both source repositories use ``backend/achievement_routes.py`` blob
``c6410bfd3bbde13454b2641a7982838893d970d9``. The source achievement catalog,
FastAPI routes, MongoDB clients and wallet/inventory mutations remain source-
owned. This module promotes only portable normalization, qualification, progress,
claim planning and daily-streak semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence


DEFAULT_MAX_STATS = frozenset({"max_combo"})
DEFAULT_SIGNAL_REQUIREMENTS = frozenset(
    {"level", "guild_joined", "guild_created", "special_breed"}
)


@dataclass(frozen=True, slots=True)
class AchievementRequirement:
    kind: str
    count: int


@dataclass(frozen=True, slots=True)
class AchievementSpec:
    id: str
    name: str
    category: str
    requirement: AchievementRequirement
    rewards: Mapping[str, Any] = field(default_factory=dict)
    hidden: bool = False
    description: str = ""
    icon: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AchievementState:
    stats: Mapping[str, int] = field(default_factory=dict)
    unlocked: frozenset[str] = frozenset()
    claimed: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        normalized_stats: dict[str, int] = {}
        for raw_key, raw_value in self.stats.items():
            key = _normalized_token(raw_key, "achievement stat")
            value = _nonnegative_int(raw_value, f"achievement stat {key}")
            if key in normalized_stats:
                raise ValueError(f"duplicate achievement stat: {key}")
            normalized_stats[key] = value

        unlocked = _id_set(self.unlocked, "unlocked achievement")
        claimed = _id_set(self.claimed, "claimed achievement")
        if not claimed.issubset(unlocked):
            dangling = ", ".join(sorted(claimed.difference(unlocked)))
            raise ValueError(f"claimed achievements must be unlocked first: {dangling}")

        object.__setattr__(self, "stats", normalized_stats)
        object.__setattr__(self, "unlocked", unlocked)
        object.__setattr__(self, "claimed", claimed)


@dataclass(frozen=True, slots=True)
class AchievementRewardPlan:
    increments: Mapping[str, int] = field(default_factory=dict)
    titles: tuple[str, ...] = ()
    items: tuple[str, ...] = ()
    signals: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DailyRewardSpec:
    day: int
    rewards: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class DailyRewardStatus:
    current_streak: int
    last_claim: date | None
    can_claim: bool
    reward: DailyRewardSpec


@dataclass(frozen=True, slots=True)
class DailyClaimPlan:
    streak: int
    reward: DailyRewardSpec
    claim_date: date
    increments: Mapping[str, int]
    items: tuple[str, ...]
    signals: Mapping[str, Any] = field(default_factory=dict)


def _normalized_text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _normalized_token(value: object, field_name: str) -> str:
    return _normalized_text(value, field_name).lower()


def _nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")
    try:
        numeric = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if numeric < 0:
        raise ValueError(f"{field_name} must not be negative")
    return numeric


def _positive_int(value: object, field_name: str) -> int:
    numeric = _nonnegative_int(value, field_name)
    if numeric < 1:
        raise ValueError(f"{field_name} must be positive")
    return numeric


def _id_set(values: Sequence[str] | frozenset[str], field_name: str) -> frozenset[str]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} ids must be a sequence")
    normalized: set[str] = set()
    for value in values:
        item_id = _normalized_text(value, f"{field_name} id")
        if item_id in normalized:
            raise ValueError(f"duplicate {field_name} id: {item_id}")
        normalized.add(item_id)
    return frozenset(normalized)


def achievement_from_record(record: Mapping[str, Any]) -> AchievementSpec:
    """Normalize one source-shaped achievement definition."""

    if not isinstance(record, Mapping):
        raise TypeError("achievement record must be a mapping")

    achievement_id = _normalized_text(record.get("id"), "achievement id")
    name = _normalized_text(record.get("name"), "achievement name")
    category = _normalized_token(record.get("category"), "achievement category")

    raw_requirement = record.get("requirement")
    if not isinstance(raw_requirement, Mapping):
        raise TypeError("achievement requirement must be a mapping")
    requirement = AchievementRequirement(
        kind=_normalized_token(
            raw_requirement.get("type"),
            "achievement requirement type",
        ),
        count=_positive_int(
            raw_requirement.get("count"),
            "achievement requirement count",
        ),
    )

    hidden = record.get("hidden", False)
    if not isinstance(hidden, bool):
        raise TypeError("achievement hidden must be a boolean")

    description = str(record.get("description") or "").strip()
    icon = str(record.get("icon") or "").strip()

    rewards: dict[str, Any] = {}
    reward_fields = {
        "xp_reward": "xp",
        "coin_reward": "coins",
        "gem_reward": "gems",
        "title_reward": "title",
        "item_reward": "item",
    }
    for source_key, target_key in reward_fields.items():
        if source_key not in record or record[source_key] is None:
            continue
        value = record[source_key]
        if target_key in {"xp", "coins", "gems"}:
            rewards[target_key] = _nonnegative_int(value, f"achievement reward {target_key}")
        else:
            rewards[target_key] = _normalized_text(value, f"achievement reward {target_key}")

    consumed = {
        "id",
        "name",
        "description",
        "category",
        "icon",
        "hidden",
        "requirement",
        *reward_fields,
    }
    metadata = {key: value for key, value in record.items() if key not in consumed}
    return AchievementSpec(
        id=achievement_id,
        name=name,
        category=category,
        requirement=requirement,
        rewards=rewards,
        hidden=hidden,
        description=description,
        icon=icon,
        metadata=metadata,
    )


def update_stat(
    state: AchievementState,
    stat_type: str,
    amount: int = 1,
    *,
    allowed_stats: Sequence[str] | None = None,
    max_stats: frozenset[str] = DEFAULT_MAX_STATS,
) -> AchievementState:
    """Apply source-compatible additive or max-style stat progress."""

    stat = _normalized_token(stat_type, "achievement stat type")
    numeric_amount = _nonnegative_int(amount, "achievement stat amount")

    if allowed_stats is not None:
        allowed = {
            _normalized_token(value, "allowed achievement stat")
            for value in allowed_stats
        }
        if stat not in allowed:
            raise ValueError(f"unsupported achievement stat: {stat}")

    normalized_max_stats = {
        _normalized_token(value, "max achievement stat") for value in max_stats
    }
    stats = dict(state.stats)
    current = stats.get(stat, 0)
    stats[stat] = max(current, numeric_amount) if stat in normalized_max_stats else current + numeric_amount
    return AchievementState(
        stats=stats,
        unlocked=state.unlocked,
        claimed=state.claimed,
    )


def requirement_value(
    achievement: AchievementSpec,
    state: AchievementState,
    *,
    signals: Mapping[str, Any] | None = None,
) -> int:
    """Resolve current progress for one requirement without persistence calls."""

    kind = achievement.requirement.kind
    if kind in state.stats:
        return state.stats[kind]

    signal_map = dict(signals or {})
    if kind not in signal_map:
        return 0
    raw = signal_map[kind]
    if isinstance(raw, bool):
        return 1 if raw else 0
    return _nonnegative_int(raw, f"achievement signal {kind}")


def qualifies(
    achievement: AchievementSpec,
    state: AchievementState,
    *,
    signals: Mapping[str, Any] | None = None,
) -> bool:
    if achievement.id in state.unlocked:
        return False
    return requirement_value(achievement, state, signals=signals) >= achievement.requirement.count


def unlock_qualified(
    achievements: Sequence[AchievementSpec],
    state: AchievementState,
    *,
    signals: Mapping[str, Any] | None = None,
) -> tuple[AchievementState, tuple[AchievementSpec, ...]]:
    """Unlock all newly qualified achievements once, preserving input order."""

    seen: set[str] = set()
    newly_unlocked: list[AchievementSpec] = []
    unlocked = set(state.unlocked)
    for achievement in achievements:
        if achievement.id in seen:
            raise ValueError(f"duplicate achievement id: {achievement.id}")
        seen.add(achievement.id)
        if achievement.id in unlocked:
            continue
        if requirement_value(achievement, state, signals=signals) >= achievement.requirement.count:
            unlocked.add(achievement.id)
            newly_unlocked.append(achievement)

    return (
        AchievementState(stats=state.stats, unlocked=frozenset(unlocked), claimed=state.claimed),
        tuple(newly_unlocked),
    )


def claim_achievement(
    achievement: AchievementSpec,
    state: AchievementState,
) -> tuple[AchievementState, AchievementRewardPlan]:
    """Plan an idempotent claim without mutating wallets or inventory."""

    if achievement.id not in state.unlocked:
        raise ValueError("achievement is not unlocked")
    if achievement.id in state.claimed:
        raise ValueError("achievement is already claimed")

    claimed = set(state.claimed)
    claimed.add(achievement.id)
    next_state = AchievementState(
        stats=state.stats,
        unlocked=state.unlocked,
        claimed=frozenset(claimed),
    )
    return next_state, reward_plan(achievement.rewards)


def reward_plan(rewards: Mapping[str, Any]) -> AchievementRewardPlan:
    if not isinstance(rewards, Mapping):
        raise TypeError("achievement rewards must be a mapping")

    increments: dict[str, int] = {}
    for currency in ("xp", "coins", "gems"):
        if currency in rewards:
            increments[currency] = _nonnegative_int(
                rewards[currency],
                f"achievement reward {currency}",
            )

    titles: tuple[str, ...] = ()
    if rewards.get("title") is not None:
        titles = (_normalized_text(rewards["title"], "achievement reward title"),)

    items: tuple[str, ...] = ()
    if rewards.get("item") is not None:
        items = (_normalized_text(rewards["item"], "achievement reward item"),)

    signals = {
        key: value
        for key, value in rewards.items()
        if key not in {"xp", "coins", "gems", "title", "item"}
    }
    return AchievementRewardPlan(
        increments=increments,
        titles=titles,
        items=items,
        signals=signals,
    )


def progress_percent(
    achievement: AchievementSpec,
    state: AchievementState,
    *,
    signals: Mapping[str, Any] | None = None,
) -> int:
    current = requirement_value(achievement, state, signals=signals)
    return min(100, int((current / achievement.requirement.count) * 100))


def project_achievement(
    achievement: AchievementSpec,
    state: AchievementState,
    *,
    signals: Mapping[str, Any] | None = None,
    include_hidden: bool = False,
) -> Mapping[str, Any]:
    """Build a UI-safe projection, masking undisclosed hidden achievements."""

    unlocked = achievement.id in state.unlocked
    if achievement.hidden and not include_hidden and not unlocked:
        return {
            "id": achievement.id,
            "name": "???",
            "description": "Hidden achievement",
            "category": "hidden",
            "icon": "❓",
            "hidden": True,
            "unlocked": False,
            "claimed": False,
        }

    return {
        "id": achievement.id,
        "name": achievement.name,
        "description": achievement.description,
        "category": achievement.category,
        "icon": achievement.icon,
        "hidden": achievement.hidden,
        "unlocked": unlocked,
        "claimed": achievement.id in state.claimed,
        "current": requirement_value(achievement, state, signals=signals),
        "target": achievement.requirement.count,
        "progress_percent": progress_percent(achievement, state, signals=signals),
        "rewards": dict(achievement.rewards),
    }


def achievement_summary(
    achievements: Sequence[AchievementSpec],
    state: AchievementState,
) -> Mapping[str, Any]:
    ids = [achievement.id for achievement in achievements]
    if len(ids) != len(set(ids)):
        raise ValueError("achievement catalog contains duplicate ids")
    known = set(ids)
    unknown_unlocked = sorted(state.unlocked.difference(known))
    unknown_claimed = sorted(state.claimed.difference(known))
    if unknown_unlocked or unknown_claimed:
        unknown = sorted(set(unknown_unlocked + unknown_claimed))
        raise KeyError(f"unknown achievements in state: {', '.join(unknown)}")

    total = len(achievements)
    unlocked = len(state.unlocked)
    claimed = len(state.claimed)
    return {
        "total": total,
        "unlocked": unlocked,
        "claimed": claimed,
        "completion_percent": round((unlocked / total) * 100, 1) if total else 0.0,
    }


def daily_reward_from_record(record: Mapping[str, Any]) -> DailyRewardSpec:
    if not isinstance(record, Mapping):
        raise TypeError("daily reward record must be a mapping")
    day = _positive_int(record.get("day"), "daily reward day")
    rewards = record.get("rewards")
    if not isinstance(rewards, Mapping):
        raise TypeError("daily reward rewards must be a mapping")
    # Validate claimable reward types without forcing the source schedule into
    # the frontier package.
    reward_plan(rewards)
    return DailyRewardSpec(day=day, rewards=dict(rewards))


def _validated_schedule(schedule: Sequence[DailyRewardSpec]) -> tuple[DailyRewardSpec, ...]:
    if not schedule:
        raise ValueError("daily reward schedule must not be empty")
    ordered = tuple(sorted(schedule, key=lambda reward: reward.day))
    expected = list(range(1, len(ordered) + 1))
    actual = [reward.day for reward in ordered]
    if actual != expected:
        raise ValueError("daily reward days must be contiguous starting at 1")
    return ordered


def _claim_date(value: date | datetime | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("daily reward datetime must be timezone-aware")
        return value.astimezone(timezone.utc).date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("daily reward last claim must be ISO date") from exc
    raise TypeError("daily reward last claim must be a date, datetime, string or None")


def daily_reward_status(
    schedule: Sequence[DailyRewardSpec],
    *,
    streak: int = 0,
    last_claim: date | datetime | str | None = None,
    today: date,
) -> DailyRewardStatus:
    """Project source-compatible streak reset and cycle semantics."""

    ordered = _validated_schedule(schedule)
    current_streak = _nonnegative_int(streak, "daily reward streak")
    previous = _claim_date(last_claim)
    if not isinstance(today, date) or isinstance(today, datetime):
        raise TypeError("today must be a date")
    if previous is not None and previous > today:
        raise ValueError("daily reward last claim cannot be in the future")

    can_claim = previous != today
    if previous is not None and (today - previous).days > 1:
        current_streak = 0

    if can_claim:
        reward_day = (current_streak % len(ordered)) + 1
    else:
        reward_day = ((max(current_streak, 1) - 1) % len(ordered)) + 1
    return DailyRewardStatus(
        current_streak=current_streak,
        last_claim=previous,
        can_claim=can_claim,
        reward=ordered[reward_day - 1],
    )


def claim_daily_reward(
    schedule: Sequence[DailyRewardSpec],
    *,
    streak: int = 0,
    last_claim: date | datetime | str | None = None,
    today: date,
) -> DailyClaimPlan:
    """Plan one daily claim; repeated same-day claims fail closed."""

    ordered = _validated_schedule(schedule)
    previous = _claim_date(last_claim)
    current_streak = _nonnegative_int(streak, "daily reward streak")
    if not isinstance(today, date) or isinstance(today, datetime):
        raise TypeError("today must be a date")
    if previous is not None and previous > today:
        raise ValueError("daily reward last claim cannot be in the future")
    if previous == today:
        raise ValueError("daily reward already claimed today")

    if previous is not None and (today - previous).days == 1:
        next_streak = current_streak + 1
    else:
        next_streak = 1

    reward = ordered[(next_streak - 1) % len(ordered)]
    plan = reward_plan(reward.rewards)
    return DailyClaimPlan(
        streak=next_streak,
        reward=reward,
        claim_date=today,
        increments=plan.increments,
        items=plan.items,
        signals={"titles": plan.titles, **dict(plan.signals)},
    )
