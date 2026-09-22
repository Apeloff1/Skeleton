"""Pure tournament state machine promoted from Lorebuffa/Openworld.

Both sources share ``backend/tournament_routes.py`` blob
``14d5c55aba152c7a6000c8fea7da8603dbdf18cf``. FastAPI, MongoDB and wallet
mutation remain source-owned. This module promotes tournament lifecycle, entry,
scoring, deterministic ranking and final payout planning.

Hardening over the source:
- positive duration/capacity and non-negative entry fees;
- entry currency allowlisting and wallet-neutral debit planning;
- joins and score updates require the tournament's actual active time window;
- score/stat deltas cannot be negative;
- one canonical score→biggest-fish→user-id ordering is used everywhere;
- finalization is impossible before end_time;
- final reward plans have a stable digest so persistence can make payout replay
  idempotent rather than awarding money before status is durably finalized.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence

from skeleton.frontier.contracts import stable_content_digest


ENTRY_CURRENCIES = frozenset({"coins", "gems"})


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


def _aware(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _reward_map(values: Mapping[str, int], field_name: str) -> Mapping[str, int]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    result: dict[str, int] = {}
    for raw_key, raw_value in values.items():
        key = _token(raw_key, f"{field_name} key")
        result[key] = _nonnegative_int(raw_value, f"{field_name}[{key!r}]")
    return MappingProxyType(result)


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
class TournamentRewardTier:
    rank_min: int
    rank_max: int
    increments: Mapping[str, int]
    trophy_type: str = "participation"

    def __post_init__(self) -> None:
        rank_min = _positive_int(self.rank_min, "reward rank_min")
        rank_max = _positive_int(self.rank_max, "reward rank_max")
        if rank_max < rank_min:
            raise ValueError("reward rank_max must be >= rank_min")
        object.__setattr__(self, "rank_min", rank_min)
        object.__setattr__(self, "rank_max", rank_max)
        object.__setattr__(self, "increments", _reward_map(self.increments, "reward increments"))
        object.__setattr__(self, "trophy_type", _token(self.trophy_type, "trophy_type"))


@dataclass(frozen=True, slots=True)
class TournamentSpec:
    id: str
    start_time: datetime
    end_time: datetime
    entry_fee: int = 0
    entry_currency: str = "coins"
    max_participants: int = 1_000
    min_casts: int = 10
    fish_requirements: tuple[str, ...] = ()
    stage_requirements: tuple[int, ...] = ()
    reward_tiers: tuple[TournamentRewardTier, ...] = ()

    def __post_init__(self) -> None:
        tournament_id = _token(self.id, "tournament id")
        start = _aware(self.start_time, "tournament start_time")
        end = _aware(self.end_time, "tournament end_time")
        if end <= start:
            raise ValueError("tournament end_time must be after start_time")
        fee = _nonnegative_int(self.entry_fee, "tournament entry_fee")
        currency = _token(self.entry_currency, "tournament entry_currency")
        if currency not in ENTRY_CURRENCIES:
            raise ValueError(f"unsupported tournament entry currency: {currency}")
        capacity = _positive_int(self.max_participants, "tournament max_participants")
        min_casts = _nonnegative_int(self.min_casts, "tournament min_casts")
        fish = _id_tuple(self.fish_requirements, "tournament fish requirements")
        if isinstance(self.stage_requirements, (str, bytes)):
            raise TypeError("stage_requirements must be an iterable")
        stages = tuple(
            _positive_int(value, "tournament stage requirement")
            for value in self.stage_requirements
        )
        if len(set(stages)) != len(stages):
            raise ValueError("duplicate tournament stage requirement")
        if not isinstance(self.reward_tiers, tuple):
            raise TypeError("reward_tiers must be a tuple")
        previous_max = 0
        for tier in sorted(self.reward_tiers, key=lambda item: item.rank_min):
            if not isinstance(tier, TournamentRewardTier):
                raise TypeError("reward_tiers must contain TournamentRewardTier values")
            if tier.rank_min <= previous_max:
                raise ValueError("tournament reward tiers must not overlap")
            previous_max = tier.rank_max
        object.__setattr__(self, "id", tournament_id)
        object.__setattr__(self, "start_time", start)
        object.__setattr__(self, "end_time", end)
        object.__setattr__(self, "entry_fee", fee)
        object.__setattr__(self, "entry_currency", currency)
        object.__setattr__(self, "max_participants", capacity)
        object.__setattr__(self, "min_casts", min_casts)
        object.__setattr__(self, "fish_requirements", fish)
        object.__setattr__(self, "stage_requirements", stages)


@dataclass(frozen=True, slots=True)
class TournamentEntry:
    user_id: str
    score: int = 0
    fish_caught: int = 0
    biggest_fish: int = 0
    perfect_catches: int = 0
    combo_max: int = 0
    casts: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "user_id", _text(self.user_id, "tournament user_id"))
        for field_name in (
            "score",
            "fish_caught",
            "biggest_fish",
            "perfect_catches",
            "combo_max",
            "casts",
        ):
            object.__setattr__(
                self,
                field_name,
                _nonnegative_int(getattr(self, field_name), f"tournament {field_name}"),
            )


@dataclass(frozen=True, slots=True)
class TournamentState:
    spec: TournamentSpec
    entries: Mapping[str, TournamentEntry] = field(default_factory=dict)
    status: str = "active"
    finalization_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.spec, TournamentSpec):
            raise TypeError("spec must be TournamentSpec")
        if not isinstance(self.entries, Mapping):
            raise TypeError("entries must be a mapping")
        entries: dict[str, TournamentEntry] = {}
        for raw_key, entry in self.entries.items():
            key = _text(raw_key, "tournament entry key")
            if not isinstance(entry, TournamentEntry):
                raise TypeError("entries must contain TournamentEntry values")
            if entry.user_id != key:
                raise ValueError("tournament entry key must match user_id")
            if key in entries:
                raise ValueError(f"duplicate tournament participant: {key}")
            entries[key] = entry
        if len(entries) > self.spec.max_participants:
            raise ValueError("tournament entries exceed max_participants")
        status = _token(self.status, "tournament status")
        if status not in {"active", "ended"}:
            raise ValueError(f"unsupported tournament status: {status}")
        finalization_id = self.finalization_id
        if status == "ended":
            if finalization_id is None:
                raise ValueError("ended tournament requires finalization_id")
            finalization_id = _text(finalization_id, "tournament finalization_id")
        elif finalization_id is not None:
            raise ValueError("active tournament cannot have finalization_id")
        object.__setattr__(self, "entries", MappingProxyType(entries))
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "finalization_id", finalization_id)


@dataclass(frozen=True, slots=True)
class TournamentJoinPlan:
    state: TournamentState
    user_id: str
    debits: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "user_id", _text(self.user_id, "join user_id"))
        object.__setattr__(self, "debits", _reward_map(self.debits, "join debits"))


def _require_active_window(state: TournamentState, now: datetime) -> datetime:
    if state.status != "active":
        raise ValueError("tournament is not active")
    current = _aware(now, "tournament now")
    if current < state.spec.start_time:
        raise ValueError("tournament has not started")
    if current >= state.spec.end_time:
        raise ValueError("tournament has ended")
    return current


def join_tournament(
    state: TournamentState,
    *,
    user_id: str,
    balances: Mapping[str, int],
    now: datetime,
) -> TournamentJoinPlan:
    if not isinstance(state, TournamentState):
        raise TypeError("state must be TournamentState")
    _require_active_window(state, now)
    user = _text(user_id, "tournament user_id")
    if user in state.entries:
        raise ValueError("user already joined tournament")
    if len(state.entries) >= state.spec.max_participants:
        raise OverflowError("tournament is full")
    balance_map = _reward_map(balances, "tournament balances")
    fee = state.spec.entry_fee
    if balance_map.get(state.spec.entry_currency, 0) < fee:
        raise PermissionError(f"insufficient {state.spec.entry_currency}")
    entries = dict(state.entries)
    entries[user] = TournamentEntry(user_id=user)
    debits = {state.spec.entry_currency: fee} if fee else {}
    return TournamentJoinPlan(
        state=replace(state, entries=entries),
        user_id=user,
        debits=debits,
    )


def update_score(
    state: TournamentState,
    *,
    user_id: str,
    score_delta: int,
    fish_caught: int = 0,
    biggest_fish: int = 0,
    perfect_catches: int = 0,
    combo_max: int = 0,
    casts: int = 0,
    now: datetime,
) -> TournamentState:
    if not isinstance(state, TournamentState):
        raise TypeError("state must be TournamentState")
    _require_active_window(state, now)
    user = _text(user_id, "tournament user_id")
    if user not in state.entries:
        raise PermissionError("user is not participating in tournament")
    score = _nonnegative_int(score_delta, "tournament score_delta")
    fish = _nonnegative_int(fish_caught, "tournament fish_caught delta")
    biggest = _nonnegative_int(biggest_fish, "tournament biggest_fish")
    perfects = _nonnegative_int(perfect_catches, "tournament perfect_catches delta")
    combo = _nonnegative_int(combo_max, "tournament combo_max")
    cast_delta = _nonnegative_int(casts, "tournament casts delta")
    entry = state.entries[user]
    updated = replace(
        entry,
        score=entry.score + score,
        fish_caught=entry.fish_caught + fish,
        biggest_fish=max(entry.biggest_fish, biggest),
        perfect_catches=entry.perfect_catches + perfects,
        combo_max=max(entry.combo_max, combo),
        casts=entry.casts + cast_delta,
    )
    entries = dict(state.entries)
    entries[user] = updated
    return replace(state, entries=entries)


def leaderboard(state: TournamentState) -> tuple[TournamentEntry, ...]:
    if not isinstance(state, TournamentState):
        raise TypeError("state must be TournamentState")
    return tuple(
        sorted(
            state.entries.values(),
            key=lambda entry: (-entry.score, -entry.biggest_fish, entry.user_id),
        )
    )


def rank_of(state: TournamentState, user_id: str) -> int:
    user = _text(user_id, "tournament user_id")
    for rank, entry in enumerate(leaderboard(state), start=1):
        if entry.user_id == user:
            return rank
    raise KeyError("user is not participating in tournament")


@dataclass(frozen=True, slots=True)
class TournamentResult:
    user_id: str
    rank: int
    score: int
    biggest_fish: int
    qualified: bool
    increments: Mapping[str, int]
    trophy_type: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "user_id", _text(self.user_id, "result user_id"))
        object.__setattr__(self, "rank", _positive_int(self.rank, "result rank"))
        object.__setattr__(self, "score", _nonnegative_int(self.score, "result score"))
        object.__setattr__(self, "biggest_fish", _nonnegative_int(self.biggest_fish, "result biggest_fish"))
        if not isinstance(self.qualified, bool):
            raise TypeError("result qualified must be a boolean")
        object.__setattr__(self, "increments", _reward_map(self.increments, "result increments"))
        object.__setattr__(self, "trophy_type", _token(self.trophy_type, "result trophy_type"))


@dataclass(frozen=True, slots=True)
class TournamentFinalizationPlan:
    state: TournamentState
    finalization_id: str
    results: tuple[TournamentResult, ...]


def _reward_for_rank(spec: TournamentSpec, rank: int) -> tuple[Mapping[str, int], str]:
    for tier in sorted(spec.reward_tiers, key=lambda item: item.rank_min):
        if tier.rank_min <= rank <= tier.rank_max:
            return tier.increments, tier.trophy_type
    return MappingProxyType({}), "participation"


def finalize_tournament(
    state: TournamentState,
    *,
    now: datetime,
) -> TournamentFinalizationPlan:
    if not isinstance(state, TournamentState):
        raise TypeError("state must be TournamentState")
    current = _aware(now, "tournament finalize now")
    if state.status != "active":
        raise ValueError("tournament is already finalized")
    if current < state.spec.end_time:
        raise ValueError("tournament cannot be finalized before end_time")
    ordered = leaderboard(state)
    result_material: list[dict[str, object]] = []
    results: list[TournamentResult] = []
    for rank, entry in enumerate(ordered, start=1):
        qualified = entry.casts >= state.spec.min_casts
        increments, trophy = _reward_for_rank(state.spec, rank) if qualified else (MappingProxyType({}), "participation")
        result = TournamentResult(
            user_id=entry.user_id,
            rank=rank,
            score=entry.score,
            biggest_fish=entry.biggest_fish,
            qualified=qualified,
            increments=increments,
            trophy_type=trophy,
        )
        results.append(result)
        result_material.append(
            {
                "user_id": result.user_id,
                "rank": result.rank,
                "score": result.score,
                "biggest_fish": result.biggest_fish,
                "qualified": result.qualified,
                "increments": dict(result.increments),
                "trophy_type": result.trophy_type,
            }
        )
    finalization_id = stable_content_digest(
        {
            "tournament_id": state.spec.id,
            "start_time": state.spec.start_time.isoformat(),
            "end_time": state.spec.end_time.isoformat(),
            "results": result_material,
        }
    )
    ended = TournamentState(
        spec=state.spec,
        entries=state.entries,
        status="ended",
        finalization_id=finalization_id,
    )
    return TournamentFinalizationPlan(
        state=ended,
        finalization_id=finalization_id,
        results=tuple(results),
    )


def source_default_reward_tiers() -> tuple[TournamentRewardTier, ...]:
    return (
        TournamentRewardTier(1, 1, {"coins": 10_000, "gems": 100}, "gold"),
        TournamentRewardTier(2, 3, {"coins": 5_000, "gems": 50}, "silver"),
        TournamentRewardTier(4, 10, {"coins": 2_500, "gems": 25}, "bronze"),
        TournamentRewardTier(11, 50, {"coins": 1_000, "gems": 10}, "participation"),
        TournamentRewardTier(51, 100, {"coins": 500}, "participation"),
    )
