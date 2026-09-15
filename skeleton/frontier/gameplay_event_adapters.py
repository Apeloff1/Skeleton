"""Integrity adapters for limited-time gameplay-event progress.

This composes :mod:`skeleton.frontier.gameplay_events` with the existing durable
``DomainEvent`` and memory surfaces. It does not introduce another transport or
persistence implementation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.events import DomainEvent
from skeleton.frontier.gameplay_events import (
    EventTimeRestriction,
    GameplayChallengeSpec,
    GameplayEventProgress,
    GameplayEventSpec,
)


_ALLOWED_ACTIONS = frozenset(
    {"joined", "progress_updated", "challenge_completed", "milestone_claimed"}
)
_HEX = frozenset("0123456789abcdef")


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if normalized != value:
        raise ValueError(f"{field_name} must be normalized")
    return value


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 1:
        raise ValueError(f"{field_name} must be positive")
    return value


def _nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


def _finite_positive_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    numeric = float(value)
    if numeric != numeric or numeric in (float("inf"), float("-inf")):
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


def _parse_aware(value: object, field_name: str) -> datetime:
    text = _text(value, field_name)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO-8601") from exc
    return _aware(parsed, field_name)


def _mapping(value: object, field_name: str) -> Mapping[Any, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return value


def _sequence(value: object, field_name: str) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence")
    return value


def _sha256(value: object, field_name: str) -> str:
    digest = _text(value, field_name)
    if len(digest) != 64 or any(character not in _HEX for character in digest):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return digest


def _int_map(value: object, field_name: str) -> dict[str, int]:
    raw = _mapping(value, field_name)
    result: dict[str, int] = {}
    for raw_key, raw_value in raw.items():
        key = _text(raw_key, f"{field_name} key")
        if key in result:
            raise ValueError(f"duplicate {field_name} key: {key}")
        result[key] = _nonnegative_int(raw_value, f"{field_name}[{key!r}]")
    return result


def gameplay_event_identity(subject_id: str, event_id: str) -> str:
    subject = _text(subject_id, "gameplay event subject_id")
    event = _text(event_id, "gameplay event id")
    return stable_content_digest(
        {"surface": "gameplay_event", "subject_id": subject, "event_id": event}
    )


def gameplay_event_spec_payload(spec: GameplayEventSpec) -> Mapping[str, Any]:
    if not isinstance(spec, GameplayEventSpec):
        raise TypeError("spec must be GameplayEventSpec")
    return {
        "id": spec.id,
        "duration_days": spec.duration_days,
        "challenges": [
            {
                "id": challenge.id,
                "target": challenge.target,
                "rewards": dict(challenge.rewards),
            }
            for challenge in spec.challenges
        ],
        "milestone_rewards": {
            str(milestone): dict(rewards)
            for milestone, rewards in spec.milestone_rewards.items()
        },
        "multipliers": dict(spec.multipliers),
        "time_restriction": (
            {
                "start_hour": spec.time_restriction.start_hour,
                "end_hour": spec.time_restriction.end_hour,
            }
            if spec.time_restriction is not None
            else None
        ),
    }


def gameplay_event_spec_digest(spec: GameplayEventSpec) -> str:
    return stable_content_digest(gameplay_event_spec_payload(spec))


def gameplay_event_progress_payload(
    progress: GameplayEventProgress,
) -> Mapping[str, Any]:
    if not isinstance(progress, GameplayEventProgress):
        raise TypeError("progress must be GameplayEventProgress")
    return {
        "event_id": progress.event_id,
        "joined_at": progress.joined_at.isoformat(),
        "points": progress.points,
        "fish_caught": dict(progress.fish_caught),
        "challenge_progress": dict(progress.challenge_progress),
        "challenges_completed": sorted(progress.challenges_completed),
        "milestones_claimed": sorted(progress.milestones_claimed),
        "event_tokens": progress.event_tokens,
    }


def gameplay_event_progress_digest(progress: GameplayEventProgress) -> str:
    return stable_content_digest(gameplay_event_progress_payload(progress))


def _validate_progress_semantics(
    progress: GameplayEventProgress,
    spec: GameplayEventSpec,
) -> None:
    if progress.event_id != spec.id:
        raise ValueError("gameplay event progress id must match specification")
    challenges = {challenge.id: challenge for challenge in spec.challenges}
    unknown_progress = set(progress.challenge_progress).difference(challenges)
    unknown_completed = set(progress.challenges_completed).difference(challenges)
    if unknown_progress or unknown_completed:
        unknown = sorted(unknown_progress | unknown_completed)
        raise ValueError(
            "gameplay event progress contains unknown challenges: "
            + ", ".join(unknown)
        )
    for challenge_id in progress.challenges_completed:
        challenge = challenges[challenge_id]
        if progress.challenge_progress.get(challenge_id, 0) < challenge.target:
            raise ValueError(
                f"completed challenge has not reached target: {challenge_id}"
            )

    unknown_milestones = progress.milestones_claimed.difference(
        spec.milestone_rewards
    )
    if unknown_milestones:
        raise ValueError(
            "gameplay event progress contains unknown milestones: "
            + ", ".join(str(value) for value in sorted(unknown_milestones))
        )
    for milestone in progress.milestones_claimed:
        if progress.points < milestone:
            raise ValueError(
                f"claimed milestone exceeds current event points: {milestone}"
            )


def gameplay_event_transition(
    progress: GameplayEventProgress,
    spec: GameplayEventSpec,
    *,
    subject_id: str,
    action: str,
    occurred_at: datetime,
) -> DomainEvent:
    subject = _text(subject_id, "gameplay event subject_id")
    normalized_action = _text(action, "gameplay event action").lower()
    if normalized_action not in _ALLOWED_ACTIONS:
        raise ValueError(f"unsupported gameplay event action: {normalized_action}")
    occurred = _aware(occurred_at, "gameplay event occurred_at")
    _validate_progress_semantics(progress, spec)

    return DomainEvent(
        topic=f"gameplay_event.{normalized_action}",
        payload={
            "subject_id": subject,
            "gameplay_event_identity_sha256": gameplay_event_identity(
                subject, spec.id
            ),
            "gameplay_event_spec_sha256": gameplay_event_spec_digest(spec),
            "gameplay_event_progress_sha256": gameplay_event_progress_digest(
                progress
            ),
            "spec": gameplay_event_spec_payload(spec),
            "progress": gameplay_event_progress_payload(progress),
        },
        occurred_at=occurred,
    )


def _spec_from_payload(value: object) -> GameplayEventSpec:
    payload = _mapping(value, "gameplay event spec payload")
    raw_challenges = _sequence(payload.get("challenges"), "gameplay event challenges")
    challenges: list[GameplayChallengeSpec] = []
    for raw_challenge in raw_challenges:
        challenge = _mapping(raw_challenge, "gameplay event challenge")
        challenges.append(
            GameplayChallengeSpec(
                id=_text(challenge.get("id"), "gameplay event challenge id"),
                target=_positive_int(
                    challenge.get("target"), "gameplay event challenge target"
                ),
                rewards=dict(
                    _mapping(
                        challenge.get("rewards"), "gameplay event challenge rewards"
                    )
                ),
            )
        )

    raw_milestones = _mapping(
        payload.get("milestone_rewards"), "gameplay event milestone_rewards"
    )
    milestones: dict[int, Mapping[str, Any]] = {}
    for raw_key, rewards in raw_milestones.items():
        key = _text(raw_key, "gameplay event milestone key")
        if not key.isdigit():
            raise ValueError("gameplay event milestone key must be digits")
        milestone = _positive_int(int(key), "gameplay event milestone")
        milestones[milestone] = dict(
            _mapping(rewards, f"gameplay event milestone {milestone} rewards")
        )

    raw_multipliers = _mapping(
        payload.get("multipliers"), "gameplay event multipliers"
    )
    multipliers = {
        _text(key, "gameplay event multiplier key"): _finite_positive_number(
            value, f"gameplay event multiplier {key}"
        )
        for key, value in raw_multipliers.items()
    }

    raw_time = payload.get("time_restriction")
    restriction = None
    if raw_time is not None:
        time_payload = _mapping(raw_time, "gameplay event time_restriction")
        restriction = EventTimeRestriction(
            start_hour=_nonnegative_int(
                time_payload.get("start_hour"), "gameplay event start_hour"
            ),
            end_hour=_nonnegative_int(
                time_payload.get("end_hour"), "gameplay event end_hour"
            ),
        )

    return GameplayEventSpec(
        id=_text(payload.get("id"), "gameplay event id"),
        duration_days=_positive_int(
            payload.get("duration_days"), "gameplay event duration_days"
        ),
        challenges=tuple(challenges),
        milestone_rewards=milestones,
        multipliers=multipliers,
        time_restriction=restriction,
    )


def _progress_from_payload(value: object) -> GameplayEventProgress:
    payload = _mapping(value, "gameplay event progress payload")
    completed = frozenset(
        _text(item, "completed gameplay event challenge")
        for item in _sequence(
            payload.get("challenges_completed"), "challenges_completed"
        )
    )
    milestones = frozenset(
        _positive_int(item, "claimed gameplay event milestone")
        for item in _sequence(payload.get("milestones_claimed"), "milestones_claimed")
    )
    return GameplayEventProgress(
        event_id=_text(payload.get("event_id"), "gameplay event progress id"),
        joined_at=_parse_aware(payload.get("joined_at"), "gameplay event joined_at"),
        points=_nonnegative_int(payload.get("points"), "gameplay event points"),
        fish_caught=_int_map(payload.get("fish_caught"), "gameplay event fish_caught"),
        challenge_progress=_int_map(
            payload.get("challenge_progress"), "gameplay event challenge_progress"
        ),
        challenges_completed=completed,
        milestones_claimed=milestones,
        event_tokens=_nonnegative_int(
            payload.get("event_tokens"), "gameplay event event_tokens"
        ),
    )


def gameplay_event_to_memory_item(event: DomainEvent) -> Mapping[str, Any]:
    if not isinstance(event, DomainEvent):
        raise TypeError("event must be DomainEvent")
    if event.topic not in {
        f"gameplay_event.{action}" for action in _ALLOWED_ACTIONS
    }:
        raise ValueError("expected a gameplay event transition")
    occurred = _aware(event.occurred_at, "gameplay event transition occurred_at")
    payload = _mapping(event.payload, "gameplay event transition payload")
    subject = _text(payload.get("subject_id"), "gameplay event subject_id")

    spec = _spec_from_payload(payload.get("spec"))
    progress = _progress_from_payload(payload.get("progress"))
    _validate_progress_semantics(progress, spec)

    identity = _sha256(
        payload.get("gameplay_event_identity_sha256"),
        "gameplay_event_identity_sha256",
    )
    if identity != gameplay_event_identity(subject, spec.id):
        raise ValueError("gameplay event identity digest mismatch")

    expected_spec_digest = _sha256(
        payload.get("gameplay_event_spec_sha256"),
        "gameplay_event_spec_sha256",
    )
    if expected_spec_digest != gameplay_event_spec_digest(spec):
        raise ValueError("gameplay event spec digest mismatch")

    expected_progress_digest = _sha256(
        payload.get("gameplay_event_progress_sha256"),
        "gameplay_event_progress_sha256",
    )
    if expected_progress_digest != gameplay_event_progress_digest(progress):
        raise ValueError("gameplay event progress digest mismatch")

    action = event.topic.removeprefix("gameplay_event.")
    return {
        "id": identity,
        "content": (
            f"gameplay event {action} {spec.id} {progress.points} points "
            f"{len(progress.challenges_completed)} challenges"
        ),
        "metadata": {
            "subject_id": subject,
            "gameplay_event_id": spec.id,
            "gameplay_event_identity_sha256": identity,
            "gameplay_event_spec_sha256": expected_spec_digest,
            "gameplay_event_progress_sha256": expected_progress_digest,
            "gameplay_event_action": action,
            "points": progress.points,
            "event_tokens": progress.event_tokens,
            "completed_challenge_count": len(progress.challenges_completed),
            "claimed_milestone_count": len(progress.milestones_claimed),
            "occurred_at": occurred.isoformat(),
        },
    }


def gameplay_event_memory_item(
    progress: GameplayEventProgress,
    spec: GameplayEventSpec,
    *,
    subject_id: str,
) -> Mapping[str, Any]:
    subject = _text(subject_id, "gameplay event subject_id")
    _validate_progress_semantics(progress, spec)
    identity = gameplay_event_identity(subject, spec.id)
    return {
        "id": identity,
        "content": (
            f"gameplay event {spec.id} {progress.points} points "
            f"{len(progress.challenges_completed)} challenges"
        ),
        "metadata": {
            "subject_id": subject,
            "gameplay_event_id": spec.id,
            "gameplay_event_identity_sha256": identity,
            "gameplay_event_spec_sha256": gameplay_event_spec_digest(spec),
            "gameplay_event_progress_sha256": gameplay_event_progress_digest(progress),
            "points": progress.points,
            "event_tokens": progress.event_tokens,
            "completed_challenge_count": len(progress.challenges_completed),
            "claimed_milestone_count": len(progress.milestones_claimed),
        },
    }
