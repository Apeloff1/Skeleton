"""Dependency-free guild policy promoted from Lorebuffa/Openworld.

Both source repositories carry the exact same ``backend/guild_routes.py`` blob
``02bfb09c1c1b57b919aa0128c3ecf5f2eb94e41f``. FastAPI, Motor/MongoDB,
chat, search and persistence remain source-owned. This module promotes the
portable domain rules and hardens them into immutable, transactional plans:
membership/rank authority, contribution-driven progression, level perks and
capacity, leadership transfer, and stake-backed guild challenges.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Mapping


MAX_GUILD_LEVEL = 10
BASE_MEMBER_CAP = 30
MEMBERS_PER_LEVEL = 5
RANK_ORDER = ("member", "elder", "co-leader")
RANK_CONTRIBUTION_REQUIREMENTS = MappingProxyType(
    {"member": 0, "elder": 2_000, "co-leader": 5_000, "leader": 0}
)
ACCEPT_APPLICATION_RANKS = frozenset({"leader", "co-leader", "elder"})
KICK_RANKS = frozenset({"leader", "co-leader"})
CHALLENGE_RANKS = frozenset({"leader", "co-leader"})
CHALLENGE_TYPES = frozenset({"fish_count", "total_score", "biggest_fish"})
CONTRIBUTION_TYPES = frozenset({"coins", "fish", "points"})

GUILD_PERKS: Mapping[int, tuple[str, ...]] = MappingProxyType(
    {
        1: (),
        2: ("bonus_xp_5",),
        3: ("bonus_xp_5", "bonus_coins_5"),
        4: ("bonus_xp_10", "bonus_coins_5", "extra_energy_10"),
        5: (
            "bonus_xp_10",
            "bonus_coins_10",
            "extra_energy_10",
            "rare_fish_boost_5",
        ),
        6: (
            "bonus_xp_15",
            "bonus_coins_10",
            "extra_energy_15",
            "rare_fish_boost_5",
        ),
        7: (
            "bonus_xp_15",
            "bonus_coins_15",
            "extra_energy_15",
            "rare_fish_boost_10",
        ),
        8: (
            "bonus_xp_20",
            "bonus_coins_15",
            "extra_energy_20",
            "rare_fish_boost_10",
            "exclusive_badge",
        ),
        9: (
            "bonus_xp_20",
            "bonus_coins_20",
            "extra_energy_20",
            "rare_fish_boost_15",
            "exclusive_badge",
        ),
        10: (
            "bonus_xp_25",
            "bonus_coins_25",
            "extra_energy_25",
            "rare_fish_boost_20",
            "exclusive_badge",
            "legendary_lure",
        ),
    }
)


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


def _rank(value: object) -> str:
    rank = _text(value, "guild rank")
    if rank not in {*RANK_ORDER, "leader"}:
        raise ValueError(f"unsupported guild rank: {rank}")
    return rank


def member_cap_for_level(level: int) -> int:
    level = _positive_int(level, "guild level")
    if level > MAX_GUILD_LEVEL:
        raise ValueError(f"guild level must not exceed {MAX_GUILD_LEVEL}")
    return BASE_MEMBER_CAP + (level - 1) * MEMBERS_PER_LEVEL


def xp_for_next_level(level: int) -> int | None:
    level = _positive_int(level, "guild level")
    if level > MAX_GUILD_LEVEL:
        raise ValueError(f"guild level must not exceed {MAX_GUILD_LEVEL}")
    if level == MAX_GUILD_LEVEL:
        return None
    return level * 1_000


@dataclass(frozen=True, slots=True)
class GuildMember:
    user_id: str
    rank: str = "member"
    contribution_points: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "user_id", _text(self.user_id, "guild member user_id"))
        object.__setattr__(self, "rank", _rank(self.rank))
        object.__setattr__(
            self,
            "contribution_points",
            _nonnegative_int(self.contribution_points, "guild member contribution_points"),
        )


@dataclass(frozen=True, slots=True)
class GuildState:
    id: str
    leader_id: str
    level: int
    experience: int
    members: Mapping[str, GuildMember]
    treasury: Mapping[str, int]
    weekly_contribution: int = 0

    def __post_init__(self) -> None:
        guild_id = _text(self.id, "guild id")
        leader_id = _text(self.leader_id, "guild leader_id")
        level = _positive_int(self.level, "guild level")
        if level > MAX_GUILD_LEVEL:
            raise ValueError(f"guild level must not exceed {MAX_GUILD_LEVEL}")
        experience = _nonnegative_int(self.experience, "guild experience")
        threshold = xp_for_next_level(level)
        if threshold is not None and experience >= threshold:
            raise ValueError("guild experience must be normalized below the next level threshold")

        if not isinstance(self.members, Mapping):
            raise TypeError("guild members must be a mapping")
        members: dict[str, GuildMember] = {}
        for raw_id, member in self.members.items():
            user_id = _text(raw_id, "guild member key")
            if not isinstance(member, GuildMember):
                raise TypeError("guild members must contain GuildMember values")
            if member.user_id != user_id:
                raise ValueError("guild member key must match member user_id")
            if user_id in members:
                raise ValueError(f"duplicate guild member: {user_id}")
            members[user_id] = member
        if leader_id not in members:
            raise ValueError("guild leader must be a member")
        leaders = [member.user_id for member in members.values() if member.rank == "leader"]
        if leaders != [leader_id]:
            raise ValueError("guild must contain exactly one rank=leader matching leader_id")
        if len(members) > member_cap_for_level(level):
            raise ValueError("guild member count exceeds level capacity")

        if not isinstance(self.treasury, Mapping):
            raise TypeError("guild treasury must be a mapping")
        treasury: dict[str, int] = {}
        for raw_key, raw_value in self.treasury.items():
            key = _text(raw_key, "guild treasury key")
            treasury[key] = _nonnegative_int(raw_value, f"guild treasury {key}")

        object.__setattr__(self, "id", guild_id)
        object.__setattr__(self, "leader_id", leader_id)
        object.__setattr__(self, "level", level)
        object.__setattr__(self, "experience", experience)
        object.__setattr__(self, "members", MappingProxyType(members))
        object.__setattr__(self, "treasury", MappingProxyType(treasury))
        object.__setattr__(
            self,
            "weekly_contribution",
            _nonnegative_int(self.weekly_contribution, "guild weekly_contribution"),
        )

    @property
    def max_members(self) -> int:
        return member_cap_for_level(self.level)

    @property
    def perks(self) -> tuple[str, ...]:
        return GUILD_PERKS[self.level]


@dataclass(frozen=True, slots=True)
class GuildContributionPlan:
    state: GuildState
    contributor_id: str
    contribution_type: str
    amount: int
    contribution_points: int
    levels_gained: int
    source_debit: int


@dataclass(frozen=True, slots=True)
class GuildChallenge:
    id: str
    challenger_guild_id: str
    defender_guild_id: str
    challenge_type: str
    target: int
    duration_hours: int = 24
    stake_coins: int = 0
    challenger_progress: int = 0
    defender_progress: int = 0
    status: str = "pending"
    winner_guild_id: str | None = None
    escrow_funded: bool = False

    def __post_init__(self) -> None:
        challenge_id = _text(self.id, "guild challenge id")
        challenger = _text(self.challenger_guild_id, "challenger guild id")
        defender = _text(self.defender_guild_id, "defender guild id")
        if challenger == defender:
            raise ValueError("guild cannot challenge itself")
        challenge_type = _text(self.challenge_type, "guild challenge type")
        if challenge_type not in CHALLENGE_TYPES:
            raise ValueError(f"unsupported guild challenge type: {challenge_type}")
        target = _positive_int(self.target, "guild challenge target")
        duration = _positive_int(self.duration_hours, "guild challenge duration_hours")
        if duration > 168:
            raise ValueError("guild challenge duration_hours must not exceed 168")
        stake = _nonnegative_int(self.stake_coins, "guild challenge stake_coins")
        challenger_progress = _nonnegative_int(
            self.challenger_progress, "challenger guild challenge progress"
        )
        defender_progress = _nonnegative_int(
            self.defender_progress, "defender guild challenge progress"
        )
        status = _text(self.status, "guild challenge status")
        if status not in {"pending", "active", "completed"}:
            raise ValueError(f"unsupported guild challenge status: {status}")
        winner = self.winner_guild_id
        if winner is not None:
            winner = _text(winner, "guild challenge winner_guild_id")
            if winner not in {challenger, defender}:
                raise ValueError("guild challenge winner must be a participant")
        if status == "completed" and winner is None:
            raise ValueError("completed guild challenge requires a winner")
        if status != "completed" and winner is not None:
            raise ValueError("only completed guild challenge may have a winner")
        if not isinstance(self.escrow_funded, bool):
            raise TypeError("guild challenge escrow_funded must be a boolean")
        if status in {"active", "completed"} and not self.escrow_funded:
            raise ValueError("active/completed guild challenge requires funded escrow")

        object.__setattr__(self, "id", challenge_id)
        object.__setattr__(self, "challenger_guild_id", challenger)
        object.__setattr__(self, "defender_guild_id", defender)
        object.__setattr__(self, "challenge_type", challenge_type)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "duration_hours", duration)
        object.__setattr__(self, "stake_coins", stake)
        object.__setattr__(self, "challenger_progress", challenger_progress)
        object.__setattr__(self, "defender_progress", defender_progress)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "winner_guild_id", winner)


@dataclass(frozen=True, slots=True)
class ChallengeAcceptancePlan:
    challenge: GuildChallenge
    challenger_state: GuildState
    defender_state: GuildState
    escrow_coins: int


@dataclass(frozen=True, slots=True)
class ChallengeProgressPlan:
    challenge: GuildChallenge
    winner_guild_id: str | None
    payout_coins: int


def initial_guild(guild_id: str, leader_id: str) -> GuildState:
    leader = GuildMember(user_id=leader_id, rank="leader")
    return GuildState(
        id=guild_id,
        leader_id=leader.user_id,
        level=1,
        experience=0,
        members={leader.user_id: leader},
        treasury={"coins": 0, "gems": 0},
    )


def _member(state: GuildState, user_id: str) -> GuildMember:
    user = _text(user_id, "guild member user_id")
    try:
        return state.members[user]
    except KeyError as exc:
        raise PermissionError("user is not a member of this guild") from exc


def can_accept_applications(state: GuildState, actor_id: str) -> bool:
    return _member(state, actor_id).rank in ACCEPT_APPLICATION_RANKS


def add_member(state: GuildState, user_id: str) -> GuildState:
    user = _text(user_id, "new guild member user_id")
    if user in state.members:
        raise ValueError("user is already a guild member")
    if len(state.members) >= state.max_members:
        raise OverflowError("guild is at member capacity")
    members = dict(state.members)
    members[user] = GuildMember(user_id=user)
    return replace(state, members=members)


def leave_member(state: GuildState, user_id: str) -> GuildState:
    member = _member(state, user_id)
    if member.rank == "leader":
        raise PermissionError("guild leader must transfer leadership before leaving")
    members = dict(state.members)
    del members[member.user_id]
    return replace(state, members=members)


def kick_member(state: GuildState, *, actor_id: str, target_id: str) -> GuildState:
    actor = _member(state, actor_id)
    target = _member(state, target_id)
    if actor.rank not in KICK_RANKS:
        raise PermissionError("actor rank cannot kick guild members")
    if target.rank == "leader":
        raise PermissionError("guild leader cannot be kicked")
    if actor.user_id == target.user_id:
        raise ValueError("use leave_member for self-removal")
    members = dict(state.members)
    del members[target.user_id]
    return replace(state, members=members)


def promote_member(state: GuildState, *, actor_id: str, target_id: str) -> GuildState:
    actor = _member(state, actor_id)
    target = _member(state, target_id)
    if actor.rank != "leader":
        raise PermissionError("only guild leader may promote members")
    if target.rank == "leader":
        raise ValueError("guild leader is already the highest rank")
    try:
        rank_index = RANK_ORDER.index(target.rank)
    except ValueError as exc:
        raise ValueError(f"unsupported promotable rank: {target.rank}") from exc
    if rank_index == len(RANK_ORDER) - 1:
        raise ValueError("member is already at highest promotable rank")
    next_rank = RANK_ORDER[rank_index + 1]
    required = RANK_CONTRIBUTION_REQUIREMENTS[next_rank]
    if target.contribution_points < required:
        raise PermissionError(
            f"promotion to {next_rank} requires {required} contribution points"
        )
    members = dict(state.members)
    members[target.user_id] = replace(target, rank=next_rank)
    return replace(state, members=members)


def transfer_leadership(
    state: GuildState,
    *,
    current_leader_id: str,
    new_leader_id: str,
) -> GuildState:
    current = _member(state, current_leader_id)
    successor = _member(state, new_leader_id)
    if current.user_id != state.leader_id or current.rank != "leader":
        raise PermissionError("only current guild leader may transfer leadership")
    if successor.user_id == current.user_id:
        raise ValueError("new guild leader must be a different member")
    members = dict(state.members)
    members[current.user_id] = replace(current, rank="co-leader")
    members[successor.user_id] = replace(successor, rank="leader")
    return replace(state, leader_id=successor.user_id, members=members)


def contribute(
    state: GuildState,
    *,
    user_id: str,
    contribution_type: str,
    amount: int,
    available_amount: int,
) -> GuildContributionPlan:
    member = _member(state, user_id)
    kind = _text(contribution_type, "guild contribution type")
    if kind not in CONTRIBUTION_TYPES:
        raise ValueError(f"unsupported guild contribution type: {kind}")
    amount = _positive_int(amount, "guild contribution amount")
    available = _nonnegative_int(available_amount, "available contribution amount")
    if available < amount:
        raise PermissionError("insufficient contributor resources")

    points = amount // 10
    members = dict(state.members)
    members[member.user_id] = replace(
        member,
        contribution_points=member.contribution_points + points,
    )
    treasury = dict(state.treasury)
    treasury[kind] = treasury.get(kind, 0) + amount

    level = state.level
    experience = state.experience + points
    levels_gained = 0
    while level < MAX_GUILD_LEVEL:
        threshold = xp_for_next_level(level)
        assert threshold is not None
        if experience < threshold:
            break
        experience -= threshold
        level += 1
        levels_gained += 1

    next_state = GuildState(
        id=state.id,
        leader_id=state.leader_id,
        level=level,
        experience=experience,
        members=members,
        treasury=treasury,
        weekly_contribution=state.weekly_contribution + amount,
    )
    return GuildContributionPlan(
        state=next_state,
        contributor_id=member.user_id,
        contribution_type=kind,
        amount=amount,
        contribution_points=points,
        levels_gained=levels_gained,
        source_debit=amount,
    )


def create_challenge(
    challenger: GuildState,
    defender: GuildState,
    *,
    actor_id: str,
    challenge_id: str,
    challenge_type: str,
    target: int,
    duration_hours: int = 24,
    stake_coins: int = 0,
) -> GuildChallenge:
    actor = _member(challenger, actor_id)
    if actor.rank not in CHALLENGE_RANKS:
        raise PermissionError("actor rank cannot start guild challenges")
    stake = _nonnegative_int(stake_coins, "guild challenge stake_coins")
    if challenger.treasury.get("coins", 0) < stake:
        raise PermissionError("challenger guild treasury cannot cover stake")
    return GuildChallenge(
        id=challenge_id,
        challenger_guild_id=challenger.id,
        defender_guild_id=defender.id,
        challenge_type=challenge_type,
        target=target,
        duration_hours=duration_hours,
        stake_coins=stake,
    )


def _debit_coins(state: GuildState, amount: int) -> GuildState:
    balance = state.treasury.get("coins", 0)
    if balance < amount:
        raise PermissionError("guild treasury cannot cover challenge stake")
    treasury = dict(state.treasury)
    treasury["coins"] = balance - amount
    return replace(state, treasury=treasury)


def accept_challenge(
    challenge: GuildChallenge,
    *,
    challenger: GuildState,
    defender: GuildState,
    defender_actor_id: str,
) -> ChallengeAcceptancePlan:
    if challenge.status != "pending" or challenge.escrow_funded:
        raise ValueError("guild challenge is not pending acceptance")
    if challenger.id != challenge.challenger_guild_id:
        raise ValueError("challenger state does not match guild challenge")
    if defender.id != challenge.defender_guild_id:
        raise ValueError("defender state does not match guild challenge")
    actor = _member(defender, defender_actor_id)
    if actor.rank not in CHALLENGE_RANKS:
        raise PermissionError("actor rank cannot accept guild challenges")

    # Preflight both balances before producing either debit so callers can apply
    # the returned pair transactionally without a one-sided stake mutation.
    stake = challenge.stake_coins
    if challenger.treasury.get("coins", 0) < stake:
        raise PermissionError("challenger guild treasury cannot cover stake")
    if defender.treasury.get("coins", 0) < stake:
        raise PermissionError("defender guild treasury cannot cover stake")

    challenger_state = _debit_coins(challenger, stake)
    defender_state = _debit_coins(defender, stake)
    active = replace(challenge, status="active", escrow_funded=True)
    return ChallengeAcceptancePlan(
        challenge=active,
        challenger_state=challenger_state,
        defender_state=defender_state,
        escrow_coins=stake * 2,
    )


def record_challenge_progress(
    challenge: GuildChallenge,
    *,
    guild_id: str,
    progress_value: int,
) -> ChallengeProgressPlan:
    if challenge.status != "active" or not challenge.escrow_funded:
        raise ValueError("guild challenge is not active")
    guild = _text(guild_id, "guild challenge progress guild_id")
    if guild not in {challenge.challenger_guild_id, challenge.defender_guild_id}:
        raise ValueError("guild is not a participant in this challenge")
    value = _nonnegative_int(progress_value, "guild challenge progress_value")

    challenger_progress = challenge.challenger_progress
    defender_progress = challenge.defender_progress
    if challenge.challenge_type == "biggest_fish":
        if guild == challenge.challenger_guild_id:
            challenger_progress = max(challenger_progress, value)
        else:
            defender_progress = max(defender_progress, value)
    else:
        if guild == challenge.challenger_guild_id:
            challenger_progress += value
        else:
            defender_progress += value

    winner: str | None = None
    if challenger_progress >= challenge.target:
        winner = challenge.challenger_guild_id
    if defender_progress >= challenge.target:
        if winner is None:
            winner = challenge.defender_guild_id
        elif defender_progress > challenger_progress:
            winner = challenge.defender_guild_id

    if winner is None:
        updated = replace(
            challenge,
            challenger_progress=challenger_progress,
            defender_progress=defender_progress,
        )
        return ChallengeProgressPlan(updated, None, 0)

    completed = replace(
        challenge,
        challenger_progress=challenger_progress,
        defender_progress=defender_progress,
        status="completed",
        winner_guild_id=winner,
    )
    return ChallengeProgressPlan(completed, winner, challenge.stake_coins * 2)


def apply_challenge_payout(
    state: GuildState,
    progress: ChallengeProgressPlan,
) -> GuildState:
    if progress.winner_guild_id is None or progress.payout_coins <= 0:
        if progress.winner_guild_id is None and progress.payout_coins != 0:
            raise ValueError("challenge payout without a winner is invalid")
        return state
    if state.id != progress.winner_guild_id:
        raise ValueError("challenge payout may only be applied to the winner")
    treasury = dict(state.treasury)
    treasury["coins"] = treasury.get("coins", 0) + progress.payout_coins
    return replace(state, treasury=treasury)
