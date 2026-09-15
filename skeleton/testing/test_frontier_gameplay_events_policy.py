from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from skeleton.frontier.gameplay_events import (
    EventTimeRestriction,
    GameplayEventProgress,
    claim_event_milestone,
    event_spec_from_record,
    event_time_restriction_active,
    event_window,
    event_window_active,
    initial_event_progress,
    next_event_milestone,
    season_for_date,
    update_event_progress,
)


NOW = datetime(2026, 9, 15, 20, 0, tzinfo=timezone.utc)


def _event_record():
    return {
        "id": "spring_bloom",
        "duration_days": 14,
        "special_fish": [{"id": "catalog-owned"}],
        "shop_items": [{"id": "source-owned"}],
        "challenges": [
            {
                "id": "spring_catches",
                "target": 100,
                "reward": {"coins": 5000, "event_tokens": 50},
            },
        ],
        "rewards": {
            1000: {"coins": 1000, "event_tokens": 100},
            5000: {"gems": 25, "title": "Spring Champion"},
        },
        "multipliers": {"xp": 2.0, "rare_chance": 1.5},
        "time_restriction": {"start_hour": 20, "end_hour": 6},
    }


def test_source_record_normalizes_only_portable_policy_fields():
    spec = event_spec_from_record(_event_record())

    assert spec.id == "spring_bloom"
    assert spec.duration_days == 14
    assert [challenge.id for challenge in spec.challenges] == ["spring_catches"]
    assert spec.challenges[0].target == 100
    assert spec.challenges[0].rewards["event_tokens"] == 50
    assert spec.milestone_rewards[1000]["coins"] == 1000
    assert spec.multipliers == {"rare_chance": 1.5, "xp": 2.0}
    assert spec.time_restriction == EventTimeRestriction(20, 6)
    assert not hasattr(spec, "special_fish")
    assert not hasattr(spec, "shop_items")


def test_season_policy_is_deterministic_and_clock_free():
    assert season_for_date(date(2026, 3, 1)) == "spring"
    assert season_for_date(date(2026, 6, 1)) == "summer"
    assert season_for_date(date(2026, 9, 1)) == "autumn"
    assert season_for_date(date(2026, 12, 1)) == "winter"


def test_event_window_uses_half_open_interval():
    spec = event_spec_from_record(_event_record())
    window = event_window(spec, starts_at=NOW)

    assert event_window_active(window, at=NOW)
    assert event_window_active(window, at=window.ends_at - timedelta(microseconds=1))
    assert not event_window_active(window, at=window.ends_at)
    assert not event_window_active(window, at=NOW - timedelta(microseconds=1))


def test_midnight_time_restriction_handles_wraparound():
    restriction = EventTimeRestriction(20, 6)
    assert event_time_restriction_active(restriction, at=NOW)
    assert event_time_restriction_active(
        restriction, at=NOW.replace(hour=23)
    )
    assert event_time_restriction_active(
        restriction, at=NOW.replace(hour=5)
    )
    assert not event_time_restriction_active(
        restriction, at=NOW.replace(hour=6)
    )
    assert not event_time_restriction_active(
        restriction, at=NOW.replace(hour=12)
    )


def test_progress_completion_is_single_shot_and_plans_external_reward():
    spec = event_spec_from_record(_event_record())
    progress = initial_event_progress(spec, joined_at=NOW)

    first = update_event_progress(
        progress,
        spec,
        points_earned=600,
        fish_caught={"cherry_koi": 3},
        challenge_progress={"spring_catches": 100},
    )
    assert first.progress.points == 600
    assert first.progress.fish_caught == {"cherry_koi": 3}
    assert first.progress.event_tokens == 50
    assert first.progress.challenges_completed == frozenset({"spring_catches"})
    assert len(first.newly_completed) == 1
    assert first.newly_completed[0].event_tokens_awarded == 50
    assert first.newly_completed[0].external_reward.increments == {"coins": 5000}

    repeated = update_event_progress(
        first.progress,
        spec,
        challenge_progress={"spring_catches": 1},
    )
    assert repeated.progress.event_tokens == 50
    assert repeated.newly_completed == ()


def test_negative_progress_and_unknown_challenges_fail_closed():
    spec = event_spec_from_record(_event_record())
    progress = initial_event_progress(spec, joined_at=NOW)

    with pytest.raises(ValueError, match="must not be negative"):
        update_event_progress(progress, spec, points_earned=-1)
    with pytest.raises(ValueError, match="unknown challenges"):
        update_event_progress(
            progress,
            spec,
            challenge_progress={"forged_challenge": 1000},
        )


def test_next_milestone_and_claim_are_idempotent_wallet_neutral_plans():
    spec = event_spec_from_record(_event_record())
    progress = update_event_progress(
        initial_event_progress(spec, joined_at=NOW),
        spec,
        points_earned=1500,
    ).progress

    assert next_event_milestone(progress, spec) == 5000
    claim = claim_event_milestone(progress, spec, milestone=1000)
    assert claim.progress.milestones_claimed == frozenset({1000})
    assert claim.progress.event_tokens == 100
    assert claim.event_tokens_awarded == 100
    assert claim.external_reward.increments == {"coins": 1000}

    with pytest.raises(ValueError, match="already claimed"):
        claim_event_milestone(claim.progress, spec, milestone=1000)
    with pytest.raises(ValueError, match="not been reached"):
        claim_event_milestone(claim.progress, spec, milestone=5000)
    with pytest.raises(KeyError, match="not defined"):
        claim_event_milestone(claim.progress, spec, milestone=2500)


def test_progress_must_match_event_and_known_catalog_ids():
    spec = event_spec_from_record(_event_record())
    wrong_event = GameplayEventProgress(event_id="other", joined_at=NOW)
    with pytest.raises(ValueError, match="must match event specification"):
        update_event_progress(wrong_event, spec)

    corrupted = GameplayEventProgress(
        event_id=spec.id,
        joined_at=NOW,
        challenge_progress={"forged": 1},
    )
    with pytest.raises(ValueError, match="unknown challenges"):
        update_event_progress(corrupted, spec)


def test_reward_and_multiplier_inputs_reject_unsafe_values():
    bad_reward = _event_record()
    bad_reward["challenges"] = [
        {"id": "bad", "target": 1, "reward": {"shell": "nope"}}
    ]
    with pytest.raises(ValueError, match="unsupported challenge reward"):
        event_spec_from_record(bad_reward)

    bad_multiplier = _event_record()
    bad_multiplier["multipliers"] = {"xp": float("inf")}
    with pytest.raises(ValueError, match="finite"):
        event_spec_from_record(bad_multiplier)

    with pytest.raises(ValueError, match="equal start/end"):
        EventTimeRestriction(6, 6)
