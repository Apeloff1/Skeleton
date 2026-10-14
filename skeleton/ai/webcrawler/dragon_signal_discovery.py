"""Blend consented engagement signals with watch-history video discovery.

The output remains a proposal requiring approval. Negative signals suppress
recommendations; they never trigger automatic media acquisition.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from .dragon_interest_signals import InterestProfile
from .dragon_video_discovery import VideoCandidate, VideoProposal, rank_similar_videos
from .dragon_video_history import VideoVisit


@dataclass(frozen=True)
class SignalDiscoveryPolicy:
    max_results: int = 20
    negative_suppression: float = -0.5
    signal_boost: float = 1.0
    min_score: float = 0.05


def rank_signal_aware_videos(
    history: tuple[VideoVisit, ...],
    candidates: tuple[VideoCandidate, ...],
    profile: InterestProfile,
    *,
    policy: SignalDiscoveryPolicy = SignalDiscoveryPolicy(),
    consent: bool = False,
) -> tuple[VideoProposal, ...]:
    if not consent:
        raise PermissionError("signal-aware discovery requires consent")
    if not 1 <= policy.max_results <= 100:
        raise ValueError("invalid result budget")
    if not isfinite(policy.negative_suppression) or not -10 <= policy.negative_suppression <= 0:
        raise ValueError("invalid suppression threshold")
    if not isfinite(policy.signal_boost) or not isfinite(policy.min_score) or not 0 <= policy.signal_boost <= 10 or not 0 <= policy.min_score <= 100:
        raise ValueError("invalid scoring policy")

    # Retain canonical URL checks, seen-video exclusions and deterministic ordering.
    base = rank_similar_videos(history, candidates, max_results=100)
    weights = {topic.tag: topic.score for topic in profile.topics}
    ranked = []
    for proposal in base:
        negatives = tuple(tag for tag in proposal.shared_tags
                          if weights.get(tag, 0) <= policy.negative_suppression)
        if negatives:
            continue
        positive = sum(max(0.0, weights.get(tag, 0)) for tag in proposal.shared_tags)
        score = proposal.score + policy.signal_boost * positive
        if score < policy.min_score:
            continue
        explanation = proposal.reason
        if positive:
            explanation += "; supported by opt-in engagement signals"
        ranked.append(VideoProposal(
            proposal.proposal_id, proposal.url, proposal.title, explanation,
            round(score, 6), proposal.shared_tags, True
        ))
    ranked.sort(key=lambda item: (-item.score, item.url))
    return tuple(ranked[:policy.max_results])
