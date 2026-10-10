"""Bounded, explainable video-interest signals for the dragon companion.

Signals are explicit opt-in observations. They are not permission to download,
watch, transcribe, or retain any video. No network calls occur here.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
from math import exp, isfinite
from typing import Iterable
import re


class SignalKind(str, Enum):
    VIEW_PROGRESS = "view_progress"
    REWATCH = "rewatch"
    LIKE = "like"
    DISLIKE = "dislike"
    SAVE = "save"
    SKIP = "skip"
    SEARCH = "search"
    CONVERSATION_INTEREST = "conversation_interest"
    EXPLICIT_TOPIC = "explicit_topic"


@dataclass(frozen=True)
class InterestSignal:
    signal_id: str
    kind: SignalKind
    tags: tuple[str, ...]
    observed_at: float
    strength: float = 1.0
    source_id: str = ""
    consent: bool = False


@dataclass(frozen=True)
class SignalPolicy:
    half_life_days: float = 30.0
    max_age_days: float = 365.0
    max_signals: int = 5000
    max_topics: int = 256
    min_abs_weight: float = 0.01
    negative_floor: float = -10.0
    positive_ceiling: float = 10.0


@dataclass(frozen=True)
class TopicInterest:
    tag: str
    score: float
    positive_evidence: int
    negative_evidence: int
    last_seen_at: float
    explanation: str


@dataclass(frozen=True)
class InterestProfile:
    topics: tuple[TopicInterest, ...]
    accepted_signals: int
    rejected_signals: int
    fingerprint: str


_TAG = re.compile(r"^[\w][\w .+#-]{0,63}$", re.UNICODE)
_WEIGHTS = {
    SignalKind.VIEW_PROGRESS: 0.5,
    SignalKind.REWATCH: 1.25,
    SignalKind.LIKE: 1.5,
    SignalKind.DISLIKE: -2.0,
    SignalKind.SAVE: 2.0,
    SignalKind.SKIP: -0.75,
    SignalKind.SEARCH: 0.4,
    SignalKind.CONVERSATION_INTEREST: 0.6,
    SignalKind.EXPLICIT_TOPIC: 2.5,
}


def normalize_tag(tag: str) -> str:
    if not isinstance(tag, str):
        raise ValueError("topic must be text")
    if any(ord(char) < 32 or ord(char) == 127 for char in tag):
        raise ValueError("invalid topic control character")
    value = " ".join(tag.casefold().split())
    if not _TAG.fullmatch(value):
        raise ValueError("invalid topic")
    return value


def validate_signal(signal: InterestSignal, now: float, policy: SignalPolicy) -> tuple[str, ...]:
    if not signal.consent:
        raise PermissionError("interest tracking requires explicit consent")
    if not signal.signal_id or len(signal.signal_id) > 128:
        raise ValueError("invalid signal id")
    if not isinstance(signal.kind, SignalKind):
        raise ValueError("invalid signal kind")
    if not isfinite(signal.observed_at) or signal.observed_at > now:
        raise ValueError("invalid signal time")
    if not isfinite(signal.strength) or not 0 <= signal.strength <= 1:
        raise ValueError("invalid signal strength")
    if not signal.tags or len(signal.tags) > 16:
        raise ValueError("invalid tag count")
    if len(signal.source_id) > 128:
        raise ValueError("source id too long")
    try:
        return tuple(sorted({normalize_tag(tag) for tag in signal.tags}))
    except (TypeError, AttributeError) as exc:
        raise ValueError("invalid signal tags") from exc


def build_interest_profile(
    signals: Iterable[InterestSignal],
    *,
    now: float,
    policy: SignalPolicy = SignalPolicy(),
) -> InterestProfile:
    if not isfinite(now):
        raise ValueError("invalid clock")
    if not (0 < policy.half_life_days <= 3650 and
            0 < policy.max_age_days <= 36500 and
            1 <= policy.max_signals <= 100000 and
            1 <= policy.max_topics <= 10000 and
            isfinite(policy.min_abs_weight) and policy.min_abs_weight >= 0 and
            isfinite(policy.negative_floor) and isfinite(policy.positive_ceiling) and
            policy.negative_floor < 0 < policy.positive_ceiling):
        raise ValueError("invalid signal policy")

    deduplicated: dict[str, tuple[InterestSignal, tuple[str, ...]]] = {}
    rejected = 0
    for index, signal in enumerate(signals):
        if index >= policy.max_signals:
            raise ValueError("signal processing budget exceeded")
        try:
            tags = validate_signal(signal, now, policy)
        except (ValueError, PermissionError):
            rejected += 1
            continue
        if now - signal.observed_at > policy.max_age_days * 86400:
            rejected += 1
            continue
        existing = deduplicated.get(signal.signal_id)
        # Deterministic tie-break, independent of arrival order.
        if existing is None or (signal.observed_at, repr(signal)) > (
            existing[0].observed_at, repr(existing[0])
        ):
            deduplicated[signal.signal_id] = (signal, tags)

    aggregates: dict[str, list[float]] = {}
    for signal, tags in sorted(deduplicated.values(), key=lambda entry: entry[0].signal_id):
        age_days = max(0.0, now - signal.observed_at) / 86400
        decay = exp(-0.6931471805599453 * age_days / policy.half_life_days)
        contribution = _WEIGHTS[signal.kind] * signal.strength * decay
        if abs(contribution) < policy.min_abs_weight:
            continue
        for tag in tags:
            values = aggregates.setdefault(tag, [0.0, 0.0, 0.0, 0.0])
            values[0] += contribution
            values[1 if contribution >= 0 else 2] += 1
            values[3] = max(values[3], signal.observed_at)

    topics = []
    for tag, (score, positive, negative, last_seen) in aggregates.items():
        bounded = min(policy.positive_ceiling, max(policy.negative_floor, score))
        if abs(bounded) < policy.min_abs_weight:
            continue
        topics.append(TopicInterest(
            tag, round(bounded, 6), int(positive), int(negative), last_seen,
            f"{int(positive)} positive and {int(negative)} negative opt-in signals"
        ))
    topics.sort(key=lambda t: (-t.score, t.tag))
    topics = topics[:policy.max_topics]
    canonical = "|".join(
        f"{t.tag}:{t.score:.6f}:{t.positive_evidence}:{t.negative_evidence}"
        for t in topics
    )
    return InterestProfile(
        tuple(topics), len(deduplicated), rejected,
        sha256(canonical.encode("utf-8")).hexdigest()
    )


def signal_search_terms(profile: InterestProfile, *, limit: int = 8) -> tuple[str, ...]:
    if not 1 <= limit <= 32:
        raise ValueError("invalid search budget")
    return tuple(topic.tag for topic in profile.topics if topic.score > 0)[:limit]
