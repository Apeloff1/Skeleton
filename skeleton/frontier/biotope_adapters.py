"""Integrity adapters for the promoted biotope progression policy.

The canonical progression primitive remains :mod:`skeleton.frontier.biotope`.
This module only projects that state across the existing frontier event/memory
boundary. It deliberately adds no second progression engine, persistence layer,
or event bus.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from skeleton.frontier.biotope import BiotopeProgress
from skeleton.frontier.contracts import stable_content_digest
from skeleton.frontier.events import DomainEvent

_ALLOWED_ACTIONS = frozenset(
    {
        "biotope_unlocked",
        "stage_unlocked",
        "stage_entered",
        "catch_recorded",
    }
)
_HEX = frozenset("0123456789abcdef")


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value or value.strip() != value:
        raise ValueError(f"{field_name} must be non-empty and normalized")
    return value


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _text(value, field_name)


def _aware(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return value


def _sequence(value: object, field_name: str) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence")
    return value


def _nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


def _positive_int(value: object, field_name: str) -> int:
    parsed = _nonnegative_int(value, field_name)
    if parsed < 1:
        raise ValueError(f"{field_name} must be positive")
    return parsed


def _sha256(value: object, field_name: str) -> str:
    digest = _text(value, field_name)
    if len(digest) != 64 or any(character not in _HEX for character in digest):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return digest


def _int_map(
    value: object,
    field_name: str,
    *,
    positive: bool = False,
) -> dict[str, int]:
    raw = _mapping(value, field_name)
    result: dict[str, int] = {}
    parser = _positive_int if positive else _nonnegative_int
    for raw_key, raw_value in raw.items():
        key = _text(raw_key, f"{field_name} key")
        if key in result:
            raise ValueError(f"duplicate {field_name} key: {key}")
        result[key] = parser(raw_value, f"{field_name}[{key!r}]")
    return result


def _validate_progress_integrity(progress: BiotopeProgress) -> None:
    """Apply persistence-boundary invariants stronger than the source document."""

    if not isinstance(progress, BiotopeProgress):
        raise TypeError("progress must be BiotopeProgress")

    unlocked = set(progress.unlocked_biotopes)
    xp_keys = set(progress.biotope_xp)
    level_keys = set(progress.biotope_level)
    catch_keys = set(progress.fish_caught_by_biotope)
    if xp_keys != unlocked or level_keys != unlocked or catch_keys != unlocked:
        raise ValueError(
            "biotope progress maps must exactly cover unlocked biotopes"
        )

    for biotope_id in sorted(unlocked):
        level = progress.biotope_level[biotope_id]
        xp = progress.biotope_xp[biotope_id]
        if xp >= level * 100:
            raise ValueError(
                f"biotope XP residue for {biotope_id} must be below the next mastery threshold"
            )

    if (progress.current_biotope is None) != (progress.current_stage is None):
        raise ValueError(
            "current_biotope and current_stage must either both be set or both be absent"
        )


def biotope_progress_payload(progress: BiotopeProgress) -> dict[str, object]:
    """Return one canonical JSON-compatible biotope progress snapshot."""

    _validate_progress_integrity(progress)
    return {
        "unlocked_biotopes": sorted(progress.unlocked_biotopes),
        "unlocked_stages": sorted(progress.unlocked_stages),
        "current_biotope": progress.current_biotope,
        "current_stage": progress.current_stage,
        "biotope_xp": dict(sorted(progress.biotope_xp.items())),
        "biotope_level": dict(sorted(progress.biotope_level.items())),
        "fish_caught_by_biotope": dict(
            sorted(progress.fish_caught_by_biotope.items())
        ),
    }


def biotope_identity(subject_id: str) -> str:
    subject = _text(subject_id, "biotope subject_id")
    return stable_content_digest({"surface": "biotope", "subject_id": subject})


def biotope_progress_digest(progress: BiotopeProgress) -> str:
    return stable_content_digest(biotope_progress_payload(progress))


def biotope_event(
    progress: BiotopeProgress,
    *,
    subject_id: str,
    action: str,
    occurred_at: datetime,
) -> DomainEvent:
    subject = _text(subject_id, "biotope subject_id")
    normalized_action = _text(action, "biotope action").lower()
    if normalized_action not in _ALLOWED_ACTIONS:
        raise ValueError(f"unsupported biotope action: {normalized_action}")
    occurred = _aware(occurred_at, "biotope occurred_at")
    payload = biotope_progress_payload(progress)
    payload.update(
        {
            "subject_id": subject,
            "biotope_identity_sha256": biotope_identity(subject),
            "biotope_progress_sha256": biotope_progress_digest(progress),
        }
    )
    return DomainEvent(
        topic=f"biotope.{normalized_action}",
        payload=payload,
        occurred_at=occurred,
    )


def _progress_from_payload(payload: Mapping[str, object]) -> BiotopeProgress:
    unlocked_biotopes = frozenset(
        _text(value, "unlocked biotope id")
        for value in _sequence(
            payload.get("unlocked_biotopes"), "unlocked_biotopes"
        )
    )
    unlocked_stages = frozenset(
        _text(value, "unlocked stage id")
        for value in _sequence(payload.get("unlocked_stages"), "unlocked_stages")
    )
    progress = BiotopeProgress(
        unlocked_biotopes=unlocked_biotopes,
        unlocked_stages=unlocked_stages,
        current_biotope=_optional_text(
            payload.get("current_biotope"), "current_biotope"
        ),
        current_stage=_optional_text(payload.get("current_stage"), "current_stage"),
        biotope_xp=_int_map(payload.get("biotope_xp"), "biotope_xp"),
        biotope_level=_int_map(
            payload.get("biotope_level"), "biotope_level", positive=True
        ),
        fish_caught_by_biotope=_int_map(
            payload.get("fish_caught_by_biotope"),
            "fish_caught_by_biotope",
        ),
    )
    _validate_progress_integrity(progress)
    return progress


def biotope_event_to_memory_item(event: DomainEvent) -> Mapping[str, Any]:
    """Validate one biotope event and project it into canonical memory metadata."""

    if not isinstance(event, DomainEvent):
        raise TypeError("event must be DomainEvent")
    if event.topic not in {f"biotope.{action}" for action in _ALLOWED_ACTIONS}:
        raise ValueError("expected a biotope transition event")

    occurred = _aware(event.occurred_at, "biotope event occurred_at")
    payload = _mapping(event.payload, "biotope event payload")
    subject = _text(payload.get("subject_id"), "biotope subject_id")

    identity = _sha256(
        payload.get("biotope_identity_sha256"), "biotope_identity_sha256"
    )
    if identity != biotope_identity(subject):
        raise ValueError("biotope event identity digest mismatch")

    expected_digest = _sha256(
        payload.get("biotope_progress_sha256"), "biotope_progress_sha256"
    )
    progress = _progress_from_payload(payload)
    actual_digest = biotope_progress_digest(progress)
    if actual_digest != expected_digest:
        raise ValueError("biotope event progress digest mismatch")

    action = event.topic.removeprefix("biotope.")
    total_catches = sum(progress.fish_caught_by_biotope.values())
    highest_mastery = max(progress.biotope_level.values(), default=0)
    return {
        "id": identity,
        "content": (
            f"biotope {action} {len(progress.unlocked_biotopes)} biotopes "
            f"{total_catches} catches"
        ),
        "metadata": {
            "subject_id": subject,
            "biotope_identity_sha256": identity,
            "biotope_progress_sha256": expected_digest,
            "biotope_action": action,
            "unlocked_biotope_count": len(progress.unlocked_biotopes),
            "unlocked_stage_count": len(progress.unlocked_stages),
            "current_biotope": progress.current_biotope,
            "current_stage": progress.current_stage,
            "total_catches": total_catches,
            "highest_mastery_level": highest_mastery,
            "occurred_at": occurred.isoformat(),
        },
    }


def biotope_progress_memory_item(
    progress: BiotopeProgress,
    *,
    subject_id: str,
) -> Mapping[str, Any]:
    subject = _text(subject_id, "biotope subject_id")
    identity = biotope_identity(subject)
    digest = biotope_progress_digest(progress)
    total_catches = sum(progress.fish_caught_by_biotope.values())
    return {
        "id": identity,
        "content": (
            f"biotope progress {len(progress.unlocked_biotopes)} biotopes "
            f"{total_catches} catches"
        ),
        "metadata": {
            "subject_id": subject,
            "biotope_identity_sha256": identity,
            "biotope_progress_sha256": digest,
            "unlocked_biotope_count": len(progress.unlocked_biotopes),
            "unlocked_stage_count": len(progress.unlocked_stages),
            "current_biotope": progress.current_biotope,
            "current_stage": progress.current_stage,
            "total_catches": total_catches,
            "highest_mastery_level": max(progress.biotope_level.values(), default=0),
        },
    }
