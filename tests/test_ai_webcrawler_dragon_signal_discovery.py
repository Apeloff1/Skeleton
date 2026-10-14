"""Integration tests for signal-aware, approval-only video discovery."""
from skeleton.ai.webcrawler.dragon_interest_signals import (
    InterestSignal, SignalKind, build_interest_profile,
)
from skeleton.ai.webcrawler.dragon_signal_discovery import rank_signal_aware_videos
from skeleton.ai.webcrawler.dragon_video_discovery import VideoCandidate
from skeleton.ai.webcrawler.dragon_video_history import VideoVisit
import pytest


def test_negative_feedback_suppresses_recommendations():
    history = (
        VideoVisit("seen", "https://example.org/watch?v=1", "Mixed topics",
                   1000, 10000, 9000, ("horror", "animation")),
    )
    candidates = (
        VideoCandidate("https://example.org/watch?v=2", "Horror", ("horror",), "catalog"),
        VideoCandidate("https://example.org/watch?v=3", "Animation", ("animation",), "catalog"),
    )
    profile = build_interest_profile([
        InterestSignal("dislike", SignalKind.DISLIKE, ("horror",), 1000, consent=True),
        InterestSignal("save", SignalKind.SAVE, ("animation",), 1000, consent=True),
    ], now=1000)
    result = rank_signal_aware_videos(history, candidates, profile, consent=True)
    assert [proposal.title for proposal in result] == ["Animation"]
    assert result[0].requires_approval
    assert "engagement" in result[0].reason


def test_signal_discovery_requires_explicit_consent():
    profile = build_interest_profile([], now=1000)
    with pytest.raises(PermissionError):
        rank_signal_aware_videos((), (), profile)


def test_results_are_stable_and_exclude_watched():
    history = (
        VideoVisit("seen", "https://example.org/watch?v=1", "Science",
                   1000, 10000, 5000, ("science",)),
    )
    candidates = (
        VideoCandidate("https://example.org/watch?v=1", "Seen", ("science",), "catalog"),
        VideoCandidate("https://example.org/watch?v=2", "New", ("science",), "catalog"),
    )
    profile = build_interest_profile([], now=1000)
    first = rank_signal_aware_videos(history, candidates, profile, consent=True)
    second = rank_signal_aware_videos(history, tuple(reversed(candidates)), profile, consent=True)
    assert first == second
    assert len(first) == 1
