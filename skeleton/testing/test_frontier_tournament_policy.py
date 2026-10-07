from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from skeleton.frontier.tournament import (
    TournamentSpec,
    TournamentState,
    finalize_tournament,
    join_tournament,
    leaderboard,
    rank_of,
    source_default_reward_tiers,
    update_score,
)


def _spec(*, entry_fee: int = 100, max_participants: int = 10, min_casts: int = 1):
    start = datetime(2026, 9, 15, 10, tzinfo=timezone.utc)
    return TournamentSpec(
        id="daily-1",
        start_time=start,
        end_time=start + timedelta(hours=2),
        entry_fee=entry_fee,
        entry_currency="coins",
        max_participants=max_participants,
        min_casts=min_casts,
        reward_tiers=source_default_reward_tiers(),
    )


def test_spec_rejects_negative_fee_bad_window_and_zero_capacity():
    start = datetime(2026, 9, 15, 10, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="negative"):
        TournamentSpec(id="t", start_time=start, end_time=start + timedelta(hours=1), entry_fee=-1)
    with pytest.raises(ValueError, match="after start_time"):
        TournamentSpec(id="t", start_time=start, end_time=start)
    with pytest.raises(ValueError, match="positive"):
        TournamentSpec(id="t", start_time=start, end_time=start + timedelta(hours=1), max_participants=0)


def test_join_requires_real_active_window_and_returns_debit_plan():
    state = TournamentState(spec=_spec())
    with pytest.raises(ValueError, match="not started"):
        join_tournament(
            state,
            user_id="u1",
            balances={"coins": 500},
            now=datetime(2026, 9, 15, 9, tzinfo=timezone.utc),
        )
    plan = join_tournament(
        state,
        user_id="u1",
        balances={"coins": 500},
        now=datetime(2026, 9, 15, 10, 30, tzinfo=timezone.utc),
    )
    assert plan.debits == {"coins": 100}
    assert "u1" in plan.state.entries


def test_join_rejects_duplicate_capacity_and_insufficient_funds():
    state = TournamentState(spec=_spec(max_participants=1))
    with pytest.raises(PermissionError, match="insufficient coins"):
        join_tournament(
            state,
            user_id="u1",
            balances={"coins": 99},
            now=datetime(2026, 9, 15, 10, 30, tzinfo=timezone.utc),
        )
    state = join_tournament(
        state,
        user_id="u1",
        balances={"coins": 100},
        now=datetime(2026, 9, 15, 10, 30, tzinfo=timezone.utc),
    ).state
    with pytest.raises(ValueError, match="already joined"):
        join_tournament(
            state,
            user_id="u1",
            balances={"coins": 100},
            now=datetime(2026, 9, 15, 10, 31, tzinfo=timezone.utc),
        )
    with pytest.raises(OverflowError, match="full"):
        join_tournament(
            state,
            user_id="u2",
            balances={"coins": 100},
            now=datetime(2026, 9, 15, 10, 31, tzinfo=timezone.utc),
        )


def test_score_updates_reject_negative_deltas_and_nonparticipants():
    now = datetime(2026, 9, 15, 10, 30, tzinfo=timezone.utc)
    state = join_tournament(
        TournamentState(spec=_spec()),
        user_id="u1",
        balances={"coins": 100},
        now=now,
    ).state
    with pytest.raises(ValueError, match="negative"):
        update_score(state, user_id="u1", score_delta=-1, now=now)
    with pytest.raises(PermissionError, match="not participating"):
        update_score(state, user_id="u2", score_delta=1, now=now)


def test_score_accumulates_counts_and_uses_max_for_tiebreak_metrics():
    now = datetime(2026, 9, 15, 10, 30, tzinfo=timezone.utc)
    state = join_tournament(
        TournamentState(spec=_spec()),
        user_id="u1",
        balances={"coins": 100},
        now=now,
    ).state
    state = update_score(
        state,
        user_id="u1",
        score_delta=100,
        fish_caught=2,
        biggest_fish=90,
        perfect_catches=1,
        combo_max=5,
        casts=2,
        now=now,
    )
    state = update_score(
        state,
        user_id="u1",
        score_delta=50,
        fish_caught=1,
        biggest_fish=80,
        perfect_catches=2,
        combo_max=3,
        casts=1,
        now=now,
    )
    entry = state.entries["u1"]
    assert entry.score == 150
    assert entry.fish_caught == 3
    assert entry.biggest_fish == 90
    assert entry.perfect_catches == 3
    assert entry.combo_max == 5
    assert entry.casts == 3


def test_leaderboard_uses_same_score_biggest_fish_user_id_order_everywhere():
    now = datetime(2026, 9, 15, 10, 30, tzinfo=timezone.utc)
    state = TournamentState(spec=_spec(entry_fee=0))
    for user in ("c", "b", "a"):
        state = join_tournament(state, user_id=user, balances={}, now=now).state
    state = update_score(state, user_id="a", score_delta=100, biggest_fish=50, casts=1, now=now)
    state = update_score(state, user_id="b", score_delta=100, biggest_fish=60, casts=1, now=now)
    state = update_score(state, user_id="c", score_delta=100, biggest_fish=60, casts=1, now=now)
    assert [entry.user_id for entry in leaderboard(state)] == ["b", "c", "a"]
    assert rank_of(state, "b") == 1
    assert rank_of(state, "c") == 2
    assert rank_of(state, "a") == 3


def test_finalize_cannot_run_early_and_is_state_bound():
    state = TournamentState(spec=_spec(entry_fee=0))
    now = datetime(2026, 9, 15, 10, 30, tzinfo=timezone.utc)
    state = join_tournament(state, user_id="u", balances={}, now=now).state
    state = update_score(state, user_id="u", score_delta=100, casts=1, now=now)
    with pytest.raises(ValueError, match="before end_time"):
        finalize_tournament(state, now=datetime(2026, 9, 15, 11, 59, tzinfo=timezone.utc))

    plan = finalize_tournament(state, now=datetime(2026, 9, 15, 12, tzinfo=timezone.utc))
    assert plan.state.status == "ended"
    assert plan.state.finalization_id == plan.finalization_id
    assert len(plan.finalization_id) == 64
    with pytest.raises(ValueError, match="already finalized"):
        finalize_tournament(plan.state, now=datetime(2026, 9, 15, 12, 1, tzinfo=timezone.utc))


def test_finalize_assigns_source_reward_tiers_after_min_cast_qualification():
    now = datetime(2026, 9, 15, 10, 30, tzinfo=timezone.utc)
    state = TournamentState(spec=_spec(entry_fee=0, min_casts=2))
    for user in ("winner", "unqualified"):
        state = join_tournament(state, user_id=user, balances={}, now=now).state
    state = update_score(state, user_id="winner", score_delta=100, biggest_fish=50, casts=2, now=now)
    state = update_score(state, user_id="unqualified", score_delta=200, biggest_fish=80, casts=1, now=now)
    plan = finalize_tournament(state, now=datetime(2026, 9, 15, 12, tzinfo=timezone.utc))

    # Rank is by performance; qualification gates payout, not ranking identity.
    assert plan.results[0].user_id == "unqualified"
    assert plan.results[0].qualified is False
    assert plan.results[0].increments == {}
    assert plan.results[1].user_id == "winner"
    assert plan.results[1].qualified is True
    assert plan.results[1].increments == {"coins": 5_000, "gems": 50}


def test_finalization_digest_is_deterministic_for_same_state():
    now = datetime(2026, 9, 15, 10, 30, tzinfo=timezone.utc)
    state = TournamentState(spec=_spec(entry_fee=0))
    state = join_tournament(state, user_id="u", balances={}, now=now).state
    state = update_score(state, user_id="u", score_delta=10, casts=1, now=now)
    end = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
    first = finalize_tournament(state, now=end)
    second = finalize_tournament(state, now=end + timedelta(minutes=1))
    assert first.finalization_id == second.finalization_id
    assert first.results == second.results
