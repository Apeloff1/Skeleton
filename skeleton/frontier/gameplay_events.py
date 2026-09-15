"""Pure limited-time gameplay-event policy from exact-shared source lineage.

Lorebuffa and Openworld share ``backend/event_routes.py`` blob
``6e7d62f7c5310374a3dad9cfdf22c1c28efc0cba``. Skeleton already owns the
canonical durable :class:`~skeleton.frontier.events.DomainEvent` transport. This
module therefore promotes only gameplay scheduling, progress, challenge and
milestone policy; it is deliberately not another event bus or persistence layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import math
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from skeleton.frontier.achievements import AchievementRewardPlan, reward_plan


_REWARD_KEYS = frozenset(
    {
        "xp",
        "coins",
        "gems",
        "event_tokens",
        "title",
        "item",
        "exclusive_fish",
        "exclusive_rod",
    }
)
_TEXT_REWARDS = frozenset({"title", "item", "exclusive_fish", "exclusive_rod"})
_INCREMENT_REWARDS = frozenset({"xp", "coins", "gems", "event_tokens"})


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if normalized != value:
        raise ValueError(f"{field_name} must be normalized")
    return value


def _token(value: object, field_name: str) -> str:
    token = _text(value, field_name).lower()
    if any(character.isspace() for character in token):
        raise ValueError(f"{field_name} must not contain whitespace")
    return token


def _nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


def _positive_int(value: object, field_name: str) -> int:
    numeric = _nonnegative_int(value, field_name)
    if numeric < 1:
        raise ValueError(f"{field_name} must be positive")
    return numeric


def _hour(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0 or value > 23:
        raise ValueError(f"{field_name} must be between 0 and 23")
    return value


def _finite_positive_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be finite")
    if numeric <= 0:
        raise ValueError(f"{field_name} must be positive")
    return numeric


def _aware(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return value


def _int_map(value: Mapping[str, int], field_name: str) -> Mapping[str, int]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    normalized: dict[str, int] = {}
    for raw_key, raw_value in value.items():
        key = _token(raw_key, f"{field_name} key")
        if key in normalized:
            raise ValueError(f"duplicate {field_name} key: {key}")
        normalized[key] = _nonnegative_int(raw_value, f"{field_name}[{key!r}]")
    return MappingProxyType(dict(sorted(normalized.items())))


def _id_set(values: Iterable[str], field_name: str) -> frozenset[str]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} must be an iterable of strings")
    result: set[str] = set()
    for raw_value in values:
        value = _token(raw_value, f"{field_name} entry")
        if value in result:
            raise ValueError(f"duplicate {field_name} entry: {value}")
        result.add(value)
    return frozenset(result)


def _milestone_set(values: Iterable[int]) -> frozenset[int]:
    if isinstance(values, (str, bytes)):
        raise TypeError("milestones_claimed must be an iterable of integers")
    result: set[int] = set()
    for raw_value in values:
        value = _positive_int(raw_value, "claimed milestone")
        if value in result:
            raise ValueError(f"duplicate claimed milestone: {value}")
        result.add(value)
    return frozenset(result)


def _reward(value: object, field_name: str) -> Mapping[str, Any]:
    raw = _mapping(value, field_name)
    normalized: dict[str, Any] = {}
    for raw_key, raw_value in raw.items():
        key = _token(raw_key, f"{field_name} key")
        if key not in _REWARD_KEYS:
            raise ValueError(f"unsupported {field_name} key: {key}")
        if key in normalized:
            raise ValueError(f"duplicate {field_name} key: {key}")
        if key in _INCREMENT_REWARDS:
            normalized[key] = _nonnegative_int(raw_value, f"{field_name} {key}")
        elif key in _TEXT_REWARDS:
            normalized[key] = _text(raw_value, f"{field_name} {key}")
    return MappingProxyType(dict(sorted(normalized.items())))


def _external_reward_plan(rewards: Mapping[str, Any]) -> AchievementRewardPlan:
    external = {key: value for key, value in rewards.items() if key != "event_tokens"}
    return reward_plan(external)


@dataclass(frozen=True, slots=True)
class GameplayChallengeSpec:
    id: str
    target: int
    rewards: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _token(self.id, "challenge id"))
        object.__setattr__(self, "target", _positive_int(self.target, "challenge target"))
        object.__setattr__(
            self,
            "rewards",
            _reward(self.rewards, "challenge reward"),
        )


@dataclass(frozen=True, slots=True)
class EventTimeRestriction:
    start_hour: int
    end_hour: int

    def __post_init__(self) -> None:
        start = _hour(self.start_hour, "event start_hour")
        end = _hour(self.end_hour, "event end_hour")
        if start == end:
            raise ValueError("event time restriction cannot have equal start/end hours")
        object.__setattr__(self, "start_hour", start)
        object.__setattr__(self, "end_hour", end)


@dataclass(frozen=True, slots=True)
class GameplayEventSpec:
    id: str
    duration_days: int
    challenges: tuple[GameplayChallengeSpec, ...] = ()
    milestone_rewards: Mapping[int, Mapping[str, Any]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    multipliers: Mapping[str, float] = field(
        default_factory=lambda: MappingProxyType({})
    )
    time_restriction: EventTimeRestriction | None = None

    def __post_init__(self) -> None:
        event_id = _token(self.id, "gameplay event id")
        duration = _positive_int(self.duration_days, "gameplay event duration_days")

        challenges: list[GameplayChallengeSpec] = []
        challenge_ids: set[str] = set()
        for challenge in self.challenges:
            if not isinstance(challenge, GameplayChallengeSpec):
                raise TypeError("event challenges must contain GameplayChallengeSpec")
            if challenge.id in challenge_ids:
                raise ValueError(f"duplicate gameplay event challenge: {challenge.id}")
            challenge_ids.add(challenge.id)
            challenges.append(challenge)

        if not isinstance(self.milestone_rewards, Mapping):
            raise TypeError("milestone_rewards must be a mapping")
        milestones: dict[int, Mapping[str, Any]] = {}
        for raw_milestone, raw_reward in self.milestone_rewards.items():
            milestone = _positive_int(raw_milestone, "event milestone")
            if milestone in milestones:
                raise ValueError(f"duplicate event milestone: {milestone}")
            milestones[milestone] = _reward(raw_reward, "milestone reward")

        if not isinstance(self.multipliers, Mapping):
            raise TypeError("event multipliers must be a mapping")
        multipliers: dict[str, float] = {}
        for raw_key, raw_value in self.multipliers.items():
            key = _token(raw_key, "event multiplier key")
            if key in multipliers:
                raise ValueError(f"duplicate event multiplier: {key}")
            multipliers[key] = _finite_positive_number(
                raw_value, f"event multiplier {key}"
            )

        if self.time_restriction is not None and not isinstance(
            self.time_restriction, EventTimeRestriction
        ):
            raise TypeError("time_restriction must be EventTimeRestriction or None")

        object.__setattr__(self, "id", event_id)
        object.__setattr__(self, "duration_days", duration)
        object.__setattr__(self, "challenges", tuple(challenges))
        object.__setattr__(
            self,
            "milestone_rewards",
            MappingProxyType(dict(sorted(milestones.items()))),
        )
        object.__setattr__(
            self,
            "multipliers",
            MappingProxyType(dict(sorted(multipliers.items()))),
        )


@dataclass(frozen=True, slots=True)
class GameplayEventProgress:
    event_id: str
    joined_at: datetime
    points: int = 0
    fish_caught: Mapping[str, int] = field(
        default_factory=lambda: MappingProxyType({})
    )
    challenge_progress: Mapping[str, int] = field(
        default_factory=lambda: MappingProxyType({})
    )
    challenges_completed: frozenset[str] = frozenset()
    milestones_claimed: frozenset[int] = frozenset()
    event_tokens: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", _token(self.event_id, "event progress id"))
        object.__setattr__(
            self, "joined_at", _aware(self.joined_at, "event joined_at")
        )
        object.__setattr__(self, "points", _nonnegative_int(self.points, "event points"))
        object.__setattr__(
            self,
            "fish_caught",
            _int_map(self.fish_caught, "event fish_caught"),
        )
        object.__setattr__(
            self,
            "challenge_progress",
            _int_map(self.challenge_progress, "event challenge_progress"),
        )
        object.__setattr__(
            self,
            "challenges_completed",
            _id_set(self.challenges_completed, "completed challenge"),
        )
        object.__setattr__(
            self,
            "milestones_claimed",
            _milestone_set(self.milestones_claimed),
        )
        object.__setattr__(
            self,
            "event_tokens",
            _nonnegative_int(self.event_tokens, "event_tokens"),
        )


@dataclass(frozen=True, slots=True)
class ChallengeCompletion:
    challenge_id: str
    external_reward: AchievementRewardPlan
    event_tokens_awarded: int = 0


@dataclass(frozen=True, slots=True)
class GameplayEventUpdatePlan:
    progress: GameplayEventProgress
    newly_completed: tuple[ChallengeCompletion, ...]


@dataclass(frozen=True, slots=True)
class GameplayMilestoneClaimPlan:
    progress: GameplayEventProgress
    milestone: int
    external_reward: AchievementRewardPlan
    event_tokens_awarded: int = 0


@dataclass(frozen=True, slots=True)
class GameplayEventWindow:
    event_id: str
    starts_at: datetime
    ends_at: datetime

    def __post_init__(self) -> None:
        event_id = _token(self.event_id, "event window id")
        starts = _aware(self.starts_at, "event starts_at")
        ends = _aware(self.ends_at, "event ends_at")
        if ends <= starts:
            raise ValueError("event ends_at must be after starts_at")
        object.__setattr__(self, "event_id", event_id)
        object.__setattr__(self, "starts_at", starts)
        object.__setattr__(self, "ends_at", ends)


def challenge_from_record(record: Mapping[str, Any]) -> GameplayChallengeSpec:
    if not isinstance(record, Mapping):
        raise TypeError("challenge record must be a mapping")
    return GameplayChallengeSpec(
        id=_token(record.get("id"), "challenge id"),
        target=_positive_int(record.get("target"), "challenge target"),
        rewards=_reward(record.get("reward", {}), "challenge reward"),
    )


def _milestone_key(value: object) -> int:
    if isinstance(value, bool):
        raise TypeError("event milestone must be an integer")
    if isinstance(value, int):
        return _positive_int(value, "event milestone")
    if isinstance(value, str) and value.isdigit():
        return _positive_int(int(value), "event milestone")
    raise TypeError("event milestone must be an integer or digit string")


def event_spec_from_record(record: Mapping[str, Any]) -> GameplayEventSpec:
    """Normalize policy fields from a source event definition.

    Presentation/catalog fields such as special fish and shop items are ignored;
    callers keep ownership of those records.
    """

    if not isinstance(record, Mapping):
        raise TypeError("gameplay event record must be a mapping")
    raw_challenges = record.get("challenges", ())
    if isinstance(raw_challenges, (str, bytes)) or not isinstance(
        raw_challenges, Sequence
    ):
        raise TypeError("gameplay event challenges must be a sequence")
    challenges = tuple(challenge_from_record(value) for value in raw_challenges)

    raw_rewards = record.get("rewards", {})
    if not isinstance(raw_rewards, Mapping):
        raise TypeError("gameplay event rewards must be a mapping")
    milestones: dict[int, Mapping[str, Any]] = {}
    for raw_milestone, raw_reward in raw_rewards.items():
        milestone = _milestone_key(raw_milestone)
        if milestone in milestones:
            raise ValueError(f"duplicate event milestone: {milestone}")
        milestones[milestone] = _reward(raw_reward, "milestone reward")

    raw_multipliers = record.get("multipliers", {})
    if not isinstance(raw_multipliers, Mapping):
        raise TypeError("gameplay event multipliers must be a mapping")

    time_restriction = None
    if record.get("time_restriction") is not None:
        raw_time = _mapping(record["time_restriction"], "event time_restriction")
        time_restriction = EventTimeRestriction(
            start_hour=_hour(raw_time.get("start_hour"), "event start_hour"),
            end_hour=_hour(raw_time.get("end_hour"), "event end_hour"),
        )

    return GameplayEventSpec(
        id=_token(record.get("id"), "gameplay event id"),
        duration_days=_positive_int(
            record.get("duration_days"), "gameplay event duration_days"
        ),
        challenges=challenges,
        milestone_rewards=milestones,
        multipliers={
            _token(key, "event multiplier key"): _finite_positive_number(
                value, f"event multiplier {key}"
            )
            for key, value in raw_multipliers.items()
        },
        time_restriction=time_restriction,
    )


def season_for_date(value: date | datetime) -> str:
    if isinstance(value, datetime):
        value = _aware(value, "season datetime").date()
    if not isinstance(value, date):
        raise TypeError("season value must be a date or datetime")
    if value.month in {3, 4, 5}:
        return "spring"
    if value.month in {6, 7, 8}:
        return "summer"
    if value.month in {9, 10, 11}:
        return "autumn"
    return "winter"


def event_window(spec: GameplayEventSpec, *, starts_at: datetime) -> GameplayEventWindow:
    if not isinstance(spec, GameplayEventSpec):
        raise TypeError("spec must be GameplayEventSpec")
    starts = _aware(starts_at, "event starts_at")
    return GameplayEventWindow(
        event_id=spec.id,
        starts_at=starts,
        ends_at=starts + timedelta(days=spec.duration_days),
    )


def event_window_active(window: GameplayEventWindow, *, at: datetime) -> bool:
    if not isinstance(window, GameplayEventWindow):
        raise TypeError("window must be GameplayEventWindow")
    current = _aware(at, "event active time")
    return window.starts_at <= current < window.ends_at


def event_time_restriction_active(
    restriction: EventTimeRestriction | None,
    *,
    at: datetime,
) -> bool:
    current = _aware(at, "event restricted time")
    if restriction is None:
        return True
    if not isinstance(restriction, EventTimeRestriction):
        raise TypeError("restriction must be EventTimeRestriction or None")
    hour = current.hour
    if restriction.start_hour < restriction.end_hour:
        return restriction.start_hour <= hour < restriction.end_hour
    return hour >= restriction.start_hour or hour < restriction.end_hour


def initial_event_progress(
    spec: GameplayEventSpec,
    *,
    joined_at: datetime,
) -> GameplayEventProgress:
    if not isinstance(spec, GameplayEventSpec):
        raise TypeError("spec must be GameplayEventSpec")
    return GameplayEventProgress(event_id=spec.id, joined_at=joined_at)


def _validate_progress_against_spec(
    progress: GameplayEventProgress,
    spec: GameplayEventSpec,
) -> None:
    if not isinstance(progress, GameplayEventProgress):
        raise TypeError("progress must be GameplayEventProgress")
    if not isinstance(spec, GameplayEventSpec):
        raise TypeError("spec must be GameplayEventSpec")
    if progress.event_id != spec.id:
        raise ValueError("event progress id must match event specification")
    challenge_ids = {challenge.id for challenge in spec.challenges}
    unknown_progress = set(progress.challenge_progress).difference(challenge_ids)
    unknown_completed = set(progress.challenges_completed).difference(challenge_ids)
    if unknown_progress or unknown_completed:
        unknown = sorted(unknown_progress | unknown_completed)
        raise ValueError(
            "event progress contains unknown challenges: " + ", ".join(unknown)
        )
    unknown_milestones = progress.milestones_claimed.difference(
        spec.milestone_rewards
    )
    if unknown_milestones:
        raise ValueError(
            "event progress contains unknown milestones: "
            + ", ".join(str(value) for value in sorted(unknown_milestones))
        )


def update_event_progress(
    progress: GameplayEventProgress,
    spec: GameplayEventSpec,
    *,
    points_earned: int = 0,
    fish_caught: Mapping[str, int] | None = None,
    challenge_progress: Mapping[str, int] | None = None,
) -> GameplayEventUpdatePlan:
    """Apply additive event progress and plan newly completed challenge rewards."""

    _validate_progress_against_spec(progress, spec)
    points_delta = _nonnegative_int(points_earned, "points_earned")
    fish_delta = _int_map(fish_caught or {}, "fish_caught delta")
    challenge_delta = _int_map(
        challenge_progress or {}, "challenge_progress delta"
    )

    challenge_ids = {challenge.id for challenge in spec.challenges}
    unknown_delta = set(challenge_delta).difference(challenge_ids)
    if unknown_delta:
        raise ValueError(
            "challenge progress delta contains unknown challenges: "
            + ", ".join(sorted(unknown_delta))
        )

    next_fish = dict(progress.fish_caught)
    for fish_id, amount in fish_delta.items():
        next_fish[fish_id] = next_fish.get(fish_id, 0) + amount

    next_challenges = dict(progress.challenge_progress)
    for challenge_id, amount in challenge_delta.items():
        next_challenges[challenge_id] = next_challenges.get(challenge_id, 0) + amount

    completed = set(progress.challenges_completed)
    newly_completed: list[ChallengeCompletion] = []
    event_tokens = progress.event_tokens
    for challenge in spec.challenges:
        if challenge.id in completed:
            continue
        if next_challenges.get(challenge.id, 0) < challenge.target:
            continue
        completed.add(challenge.id)
        tokens = int(challenge.rewards.get("event_tokens", 0))
        event_tokens += tokens
        newly_completed.append(
            ChallengeCompletion(
                challenge_id=challenge.id,
                external_reward=_external_reward_plan(challenge.rewards),
                event_tokens_awarded=tokens,
            )
        )

    next_progress = GameplayEventProgress(
        event_id=progress.event_id,
        joined_at=progress.joined_at,
        points=progress.points + points_delta,
        fish_caught=next_fish,
        challenge_progress=next_challenges,
        challenges_completed=frozenset(completed),
        milestones_claimed=progress.milestones_claimed,
        event_tokens=event_tokens,
    )
    return GameplayEventUpdatePlan(
        progress=next_progress,
        newly_completed=tuple(newly_completed),
    )


def next_event_milestone(
    progress: GameplayEventProgress,
    spec: GameplayEventSpec,
) -> int | None:
    _validate_progress_against_spec(progress, spec)
    for milestone in spec.milestone_rewards:
        if milestone > progress.points and milestone not in progress.milestones_claimed:
            return milestone
    return None


def claim_event_milestone(
    progress: GameplayEventProgress,
    spec: GameplayEventSpec,
    *,
    milestone: int,
) -> GameplayMilestoneClaimPlan:
    """Plan one idempotent milestone claim without mutating wallets/inventory."""

    _validate_progress_against_spec(progress, spec)
    threshold = _positive_int(milestone, "event milestone")
    if threshold not in spec.milestone_rewards:
        raise KeyError(f"event milestone is not defined: {threshold}")
    if threshold in progress.milestones_claimed:
        raise ValueError("event milestone is already claimed")
    if progress.points < threshold:
        raise ValueError("event milestone has not been reached")

    rewards = spec.milestone_rewards[threshold]
    tokens = int(rewards.get("event_tokens", 0))
    claimed = set(progress.milestones_claimed)
    claimed.add(threshold)
    next_progress = GameplayEventProgress(
        event_id=progress.event_id,
        joined_at=progress.joined_at,
        points=progress.points,
        fish_caught=progress.fish_caught,
        challenge_progress=progress.challenge_progress,
        challenges_completed=progress.challenges_completed,
        milestones_claimed=frozenset(claimed),
        event_tokens=progress.event_tokens + tokens,
    )
    return GameplayMilestoneClaimPlan(
        progress=next_progress,
        milestone=threshold,
        external_reward=_external_reward_plan(rewards),
        event_tokens_awarded=tokens,
    )
