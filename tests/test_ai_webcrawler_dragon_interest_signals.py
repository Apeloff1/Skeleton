"""Tests for opt-in dragon interest signals and explainable ranking."""
import pytest

from skeleton.ai.webcrawler.dragon_interest_signals import (
    InterestSignal, SignalKind, SignalPolicy, build_interest_profile,
    signal_search_terms,
)


def make_signal(signal_id, kind, tags, *, observed_at=1000.0, consent=True, strength=1.0):
    return InterestSignal(signal_id, kind, tuple(tags), observed_at, strength, consent=consent)


def test_consent_is_required_and_rejected_signals_do_not_influence_topics():
    signals = [
        make_signal("allowed", SignalKind.LIKE, ["dragons"]),
        make_signal("denied", SignalKind.SAVE, ["secret"], consent=False),
    ]
    profile = build_interest_profile(signals, now=1000.0)
    assert signal_search_terms(profile) == ("dragons",)
    assert profile.rejected_signals == 1


def test_dislikes_and_skips_reduce_recommendation_interest():
    signals = [
        make_signal("a", SignalKind.LIKE, ["horror"]),
        make_signal("b", SignalKind.DISLIKE, ["horror"]),
        make_signal("c", SignalKind.SKIP, ["horror"]),
        make_signal("d", SignalKind.SAVE, ["animation"]),
    ]
    profile = build_interest_profile(signals, now=1000.0)
    scores = {topic.tag: topic.score for topic in profile.topics}
    assert scores["horror"] < 0
    assert scores["animation"] > 0
    assert signal_search_terms(profile) == ("animation",)


def test_determinism_and_deduplication():
    signals = [
        make_signal("a", SignalKind.SAVE, ["Fantasy"]),
        make_signal("a", SignalKind.SAVE, ["Fantasy"]),
        make_signal("b", SignalKind.SEARCH, ["Art"]),
    ]
    forward = build_interest_profile(signals, now=1000.0)
    reverse = build_interest_profile(reversed(signals), now=1000.0)
    assert forward == reverse
    assert forward.accepted_signals == 2


def test_expiry_and_decay():
    now = 100 * 86400.0
    recent = make_signal("recent", SignalKind.LIKE, ["new"], observed_at=now)
    expired = make_signal("old", SignalKind.SAVE, ["old"], observed_at=0)
    profile = build_interest_profile(
        [recent, expired], now=now,
        policy=SignalPolicy(max_age_days=30),
    )
    assert signal_search_terms(profile) == ("new",)
    assert profile.rejected_signals == 1


@pytest.mark.parametrize("tags", [(), ("",), ("bad\nline",), tuple(str(i) for i in range(17))])
def test_invalid_topics_are_rejected(tags):
    profile = build_interest_profile(
        [make_signal("invalid", SignalKind.LIKE, tags)], now=1000.0
    )
    assert profile.accepted_signals == 0
    assert profile.rejected_signals == 1


def test_processing_budget_is_fail_closed():
    signals = [make_signal(str(i), SignalKind.LIKE, ["topic"]) for i in range(3)]
    with pytest.raises(ValueError, match="budget"):
        build_interest_profile(signals, now=1000.0, policy=SignalPolicy(max_signals=2))


def test_future_timestamp_is_rejected():
    profile = build_interest_profile(
        [make_signal("future", SignalKind.LIKE, ["future"], observed_at=2000)],
        now=1000.0,
    )
    assert profile.rejected_signals == 1
