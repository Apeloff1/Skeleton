"""Adapters from exact-shared biotope achievements into the canonical engine.

The source ``biotope_achievements_routes.py`` mixes a large fish catalog,
MongoDB persistence and a second achievement workflow. Skeleton already has a
canonical achievement policy, so this module promotes only source definition
normalization and explicit gameplay signals. It intentionally does not copy the
fish registry, claim persistence, wallet mutation, title storage, or a parallel
achievement state machine.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from skeleton.frontier.achievements import (
    AchievementRequirement,
    AchievementSpec,
    AchievementState,
)
from skeleton.frontier.biotope import BiotopeProgress


_BIOTOPE_STAT_ALIASES = {
    "freshwater_lake": "lake",
    "saltwater": "saltwater",
    "brackish": "brackish",
    "river": "river",
}
_REWARD_INCREMENT_KEYS = frozenset({"xp", "coins", "gems"})
_REWARD_TEXT_KEYS = frozenset({"title", "item"})


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if normalized != value:
        raise ValueError(f"{field_name} must be normalized")
    return value


def _token(value: object, field_name: str) -> str:
    token = _text(value, field_name).lower()
    if any(character.isspace() for character in token):
        raise ValueError(f"{field_name} must not contain whitespace")
    return token


def _nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


def _positive_int(value: object, field_name: str) -> int:
    numeric = _nonnegative_int(value, field_name)
    if numeric < 1:
        raise ValueError(f"{field_name} must be positive")
    return numeric


def _finite_nonnegative_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    numeric = float(value)
    if numeric != numeric or numeric in (float("inf"), float("-inf")):
        raise ValueError(f"{field_name} must be finite")
    if numeric < 0:
        raise ValueError(f"{field_name} must not be negative")
    return numeric


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return value


def _normalize_rewards(raw_rewards: object) -> dict[str, Any]:
    rewards = _mapping(raw_rewards, "biotope achievement rewards")
    normalized: dict[str, Any] = {}
    for raw_key, raw_value in rewards.items():
        key = _token(raw_key, "biotope achievement reward key")
        if key in normalized:
            raise ValueError(f"duplicate biotope achievement reward: {key}")
        if key in _REWARD_INCREMENT_KEYS:
            normalized[key] = _nonnegative_int(
                raw_value, f"biotope achievement reward {key}"
            )
        elif key in _REWARD_TEXT_KEYS:
            normalized[key] = _text(
                raw_value, f"biotope achievement reward {key}"
            )
        else:
            raise ValueError(f"unsupported biotope achievement reward: {key}")
    return normalized


def biotope_achievement_from_record(record: Mapping[str, Any]) -> AchievementSpec:
    """Normalize one biotope-achievement record for the canonical engine.

    Source records use a nested ``rewards`` mapping and sometimes use ``size``
    instead of ``count`` for their threshold. The canonical achievement engine
    has one positive integer target, so exactly one threshold form is accepted.
    Complex ``each`` semantics are retained as validated metadata for adapters
    that derive the aggregate signal explicitly.
    """

    if not isinstance(record, Mapping):
        raise TypeError("biotope achievement record must be a mapping")

    achievement_id = _token(record.get("id"), "biotope achievement id")
    name = _text(record.get("name"), "biotope achievement name")
    category = _token(record.get("category"), "biotope achievement category")
    biotope = _token(record.get("biotope"), "biotope achievement biotope")

    raw_requirement = _mapping(
        record.get("requirement"), "biotope achievement requirement"
    )
    requirement_type = _token(
        raw_requirement.get("type"), "biotope achievement requirement type"
    )
    has_count = "count" in raw_requirement
    has_size = "size" in raw_requirement
    if has_count == has_size:
        raise ValueError(
            "biotope achievement requirement must define exactly one of count or size"
        )
    threshold_key = "count" if has_count else "size"
    target = _positive_int(
        raw_requirement[threshold_key],
        f"biotope achievement requirement {threshold_key}",
    )

    metadata: dict[str, Any] = {
        "biotope": biotope,
        "source_threshold_kind": threshold_key,
    }
    if "each" in raw_requirement:
        metadata["requirement_each"] = _positive_int(
            raw_requirement["each"], "biotope achievement requirement each"
        )

    description = record.get("description", "")
    if not isinstance(description, str):
        raise TypeError("biotope achievement description must be a string")
    icon = record.get("icon", "")
    if not isinstance(icon, str):
        raise TypeError("biotope achievement icon must be a string")

    rewards = _normalize_rewards(record.get("rewards", {}))
    return AchievementSpec(
        id=achievement_id,
        name=name,
        category=category,
        requirement=AchievementRequirement(kind=requirement_type, count=target),
        rewards=rewards,
        hidden=False,
        description=description.strip(),
        icon=icon.strip(),
        metadata=metadata,
    )


def _increment(stats: dict[str, int], key: str, amount: int = 1) -> None:
    stats[key] = stats.get(key, 0) + amount


def _max_stat(stats: dict[str, int], key: str, value: int) -> None:
    stats[key] = max(stats.get(key, 0), value)


def record_biotope_achievement_catch(
    state: AchievementState,
    *,
    biotope_id: str,
    stage_id: str,
    rarity: str,
    size_cm: int | float,
    species_groups: Iterable[str] = (),
) -> AchievementState:
    """Apply one catch to canonical achievement statistics.

    The source guesses a species stat from ``fish_id.split('_')[0]``. That is
    lossy and catalog-dependent, so frontier callers must provide explicit
    ``species_groups`` such as ``("bass",)`` or ``("trout",)`` instead.
    """

    if not isinstance(state, AchievementState):
        raise TypeError("state must be AchievementState")
    biotope = _token(biotope_id, "biotope_id")
    stage = _token(stage_id, "stage_id")
    normalized_rarity = _token(rarity, "rarity")
    size = _finite_nonnegative_number(size_cm, "size_cm")
    size_stat = int(size)

    alias = _BIOTOPE_STAT_ALIASES.get(biotope, biotope)
    stats = dict(state.stats)
    _increment(stats, f"{alias}_catches")
    _increment(stats, f"{stage}_catches")
    _increment(stats, f"{normalized_rarity}_catches")
    _max_stat(stats, f"{alias}_trophy", size_stat)

    if normalized_rarity == "legendary":
        _increment(stats, f"{stage}_legendary")

    if isinstance(species_groups, (str, bytes)):
        raise TypeError("species_groups must be an iterable of explicit group names")
    seen_groups: set[str] = set()
    for raw_group in species_groups:
        group = _token(raw_group, "species group")
        if group in seen_groups:
            raise ValueError(f"duplicate species group: {group}")
        seen_groups.add(group)
        _increment(stats, f"{group}_catches")

    return AchievementState(
        stats=stats,
        unlocked=state.unlocked,
        claimed=state.claimed,
    )


def biotope_progress_achievement_signals(
    progress: BiotopeProgress,
    *,
    mastered_catch_threshold: int = 100,
) -> Mapping[str, int]:
    """Derive cross-biotope achievement signals from canonical progression.

    ``world_angler`` in the source means four biotopes with at least 100 catches
    each. The source stores that rule as ``count=4, each=100`` but its generic
    checker ignores ``each``. This adapter computes the intended aggregate signal
    explicitly instead of weakening the canonical achievement engine.
    """

    if not isinstance(progress, BiotopeProgress):
        raise TypeError("progress must be BiotopeProgress")
    threshold = _positive_int(
        mastered_catch_threshold, "mastered_catch_threshold"
    )

    signals: dict[str, int] = {}
    fished = 0
    mastered = 0
    for biotope_id, catches in sorted(progress.fish_caught_by_biotope.items()):
        alias = _BIOTOPE_STAT_ALIASES.get(biotope_id, biotope_id)
        count = _nonnegative_int(catches, f"catch count for {biotope_id}")
        signals[f"{alias}_catches"] = count
        fished += int(count > 0)
        mastered += int(count >= threshold)

    signals["biotopes_fished"] = fished
    signals["biotopes_mastered"] = mastered
    return signals


def requirement_signals_for_achievement(
    achievement: AchievementSpec,
    progress: BiotopeProgress,
) -> Mapping[str, int]:
    """Derive progress signals honoring validated source ``each`` metadata."""

    if not isinstance(achievement, AchievementSpec):
        raise TypeError("achievement must be AchievementSpec")
    each = achievement.metadata.get("requirement_each", 100)
    if isinstance(each, bool) or not isinstance(each, int):
        raise TypeError("achievement requirement_each metadata must be an integer")
    threshold = _positive_int(each, "achievement requirement_each metadata")
    return biotope_progress_achievement_signals(
        progress,
        mastered_catch_threshold=threshold,
    )
