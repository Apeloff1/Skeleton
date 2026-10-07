from __future__ import annotations

import pytest

from skeleton.frontier.guild import (
    GuildChallenge,
    GuildMember,
    GuildState,
    accept_challenge,
    add_member,
    apply_challenge_payout,
    can_accept_applications,
    contribute,
    create_challenge,
    initial_guild,
    kick_member,
    leave_member,
    member_cap_for_level,
    promote_member,
    record_challenge_progress,
    transfer_leadership,
)


def _with_member(
    state: GuildState,
    user_id: str,
    *,
    points: int = 0,
    rank: str = "member",
) -> GuildState:
    members = dict(state.members)
    members[user_id] = GuildMember(user_id, rank=rank, contribution_points=points)
    return GuildState(
        id=state.id,
        leader_id=state.leader_id,
        level=state.level,
        experience=state.experience,
        members=members,
        treasury=state.treasury,
        weekly_contribution=state.weekly_contribution,
    )


def _fund(state: GuildState, coins: int) -> GuildState:
    treasury = dict(state.treasury)
    treasury["coins"] = coins
    return GuildState(
        id=state.id,
        leader_id=state.leader_id,
        level=state.level,
        experience=state.experience,
        members=state.members,
        treasury=treasury,
        weekly_contribution=state.weekly_contribution,
    )


def test_initial_guild_matches_shared_source_baseline():
    guild = initial_guild("guild-a", "leader")

    assert guild.level == 1
    assert guild.experience == 0
    assert guild.max_members == 30
    assert guild.perks == ()
    assert guild.treasury == {"coins": 0, "gems": 0}
    assert guild.members["leader"].rank == "leader"


def test_capacity_is_derived_from_level_not_mutable_member_count():
    assert member_cap_for_level(1) == 30
    assert member_cap_for_level(10) == 75
    with pytest.raises(ValueError, match="must not exceed"):
        member_cap_for_level(11)


def test_membership_authority_preserves_source_rank_boundaries():
    guild = initial_guild("guild-a", "leader")
    guild = _with_member(guild, "elder", rank="elder")
    guild = _with_member(guild, "member")

    assert can_accept_applications(guild, "leader")
    assert can_accept_applications(guild, "elder")
    assert not can_accept_applications(guild, "member")

    with pytest.raises(PermissionError, match="cannot kick"):
        kick_member(guild, actor_id="elder", target_id="member")

    kicked = kick_member(guild, actor_id="leader", target_id="member")
    assert "member" not in kicked.members


def test_leader_cannot_leave_or_be_kicked():
    guild = _with_member(initial_guild("guild-a", "leader"), "member")

    with pytest.raises(PermissionError, match="transfer leadership"):
        leave_member(guild, "leader")
    with pytest.raises(PermissionError, match="cannot be kicked"):
        kick_member(guild, actor_id="leader", target_id="leader")


def test_promotion_uses_previously_dead_contribution_thresholds():
    guild = initial_guild("guild-a", "leader")
    guild = _with_member(guild, "candidate", points=1_999)

    with pytest.raises(PermissionError, match="2000"):
        promote_member(guild, actor_id="leader", target_id="candidate")

    members = dict(guild.members)
    members["candidate"] = GuildMember("candidate", contribution_points=5_000)
    guild = GuildState(
        id=guild.id,
        leader_id=guild.leader_id,
        level=guild.level,
        experience=guild.experience,
        members=members,
        treasury=guild.treasury,
    )
    guild = promote_member(guild, actor_id="leader", target_id="candidate")
    assert guild.members["candidate"].rank == "elder"
    guild = promote_member(guild, actor_id="leader", target_id="candidate")
    assert guild.members["candidate"].rank == "co-leader"


def test_transfer_leadership_keeps_exactly_one_leader():
    guild = _with_member(initial_guild("guild-a", "leader"), "successor")

    transferred = transfer_leadership(
        guild,
        current_leader_id="leader",
        new_leader_id="successor",
    )

    assert transferred.leader_id == "successor"
    assert transferred.members["successor"].rank == "leader"
    assert transferred.members["leader"].rank == "co-leader"
    assert sum(member.rank == "leader" for member in transferred.members.values()) == 1


def test_contribution_debits_source_and_drains_multiple_level_thresholds():
    guild = _with_member(initial_guild("guild-a", "leader"), "worker")

    plan = contribute(
        guild,
        user_id="worker",
        contribution_type="coins",
        amount=65_000,
        available_amount=65_000,
    )

    # 6,500 guild XP drains level thresholds 1k + 2k + 3k.
    assert plan.contribution_points == 6_500
    assert plan.levels_gained == 3
    assert plan.state.level == 4
    assert plan.state.experience == 500
    assert plan.state.max_members == 45
    assert plan.state.perks == ("bonus_xp_10", "bonus_coins_5", "extra_energy_10")
    assert plan.state.members["worker"].contribution_points == 6_500
    assert plan.state.treasury["coins"] == 65_000
    assert plan.state.weekly_contribution == 65_000
    assert plan.source_debit == 65_000


def test_contribution_rejects_negative_or_unfunded_mutation():
    guild = initial_guild("guild-a", "leader")

    with pytest.raises(PermissionError, match="insufficient"):
        contribute(
            guild,
            user_id="leader",
            contribution_type="coins",
            amount=100,
            available_amount=99,
        )
    with pytest.raises(ValueError, match="unsupported"):
        contribute(
            guild,
            user_id="leader",
            contribution_type="arbitrary_field",
            amount=100,
            available_amount=100,
        )


def test_challenge_acceptance_is_two_sided_and_escrow_funded():
    challenger = _fund(initial_guild("guild-a", "leader-a"), 1_000)
    defender = _fund(initial_guild("guild-b", "leader-b"), 700)
    challenge = create_challenge(
        challenger,
        defender,
        actor_id="leader-a",
        challenge_id="challenge-1",
        challenge_type="fish_count",
        target=100,
        stake_coins=500,
    )

    accepted = accept_challenge(
        challenge,
        challenger=challenger,
        defender=defender,
        defender_actor_id="leader-b",
    )

    assert accepted.challenge.status == "active"
    assert accepted.challenge.escrow_funded
    assert accepted.escrow_coins == 1_000
    assert accepted.challenger_state.treasury["coins"] == 500
    assert accepted.defender_state.treasury["coins"] == 200


def test_challenge_preflight_prevents_one_sided_stake_debit():
    challenger = _fund(initial_guild("guild-a", "leader-a"), 1_000)
    defender = _fund(initial_guild("guild-b", "leader-b"), 100)
    challenge = create_challenge(
        challenger,
        defender,
        actor_id="leader-a",
        challenge_id="challenge-1",
        challenge_type="total_score",
        target=100,
        stake_coins=500,
    )

    with pytest.raises(PermissionError, match="defender"):
        accept_challenge(
            challenge,
            challenger=challenger,
            defender=defender,
            defender_actor_id="leader-b",
        )

    assert challenger.treasury["coins"] == 1_000
    assert defender.treasury["coins"] == 100


def test_challenge_completion_emits_exact_escrow_payout_plan():
    challenger = _fund(initial_guild("guild-a", "leader-a"), 1_000)
    defender = _fund(initial_guild("guild-b", "leader-b"), 1_000)
    pending = create_challenge(
        challenger,
        defender,
        actor_id="leader-a",
        challenge_id="challenge-1",
        challenge_type="fish_count",
        target=10,
        stake_coins=250,
    )
    accepted = accept_challenge(
        pending,
        challenger=challenger,
        defender=defender,
        defender_actor_id="leader-b",
    )

    progress = record_challenge_progress(
        accepted.challenge,
        guild_id="guild-a",
        progress_value=10,
    )

    assert progress.challenge.status == "completed"
    assert progress.winner_guild_id == "guild-a"
    assert progress.payout_coins == 500
    paid = apply_challenge_payout(accepted.challenger_state, progress)
    assert paid.treasury["coins"] == 1_250


def test_biggest_fish_challenge_uses_max_semantics_not_addition():
    challenge = GuildChallenge(
        id="challenge-1",
        challenger_guild_id="guild-a",
        defender_guild_id="guild-b",
        challenge_type="biggest_fish",
        target=100,
        status="active",
        escrow_funded=True,
    )

    first = record_challenge_progress(challenge, guild_id="guild-a", progress_value=60)
    second = record_challenge_progress(
        first.challenge,
        guild_id="guild-a",
        progress_value=70,
    )

    assert second.challenge.challenger_progress == 70
    assert second.challenge.status == "active"


def test_add_member_rejects_duplicates():
    guild = initial_guild("guild-a", "leader")
    guild = add_member(guild, "member")
    with pytest.raises(ValueError, match="already"):
        add_member(guild, "member")
