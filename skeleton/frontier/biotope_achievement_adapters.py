"""Biotope achievement adapters for the canonical frontier achievement kernel.

Lorebuffa and Openworld share ``backend/biotope_achievements_routes.py`` blob
``5a06312eebf8bb21fef28b1010dfc3ccff6b6500``. The source mixes a useful
achievement catalog shape with incomplete stat maintenance: several declared
requirements (distinct species, all-biotope coverage, trophy coverage and
per-biotope mastery) are never produced by its catch recorder.

This module does not add another achievement engine. It normalizes source-shaped
records into :mod:`skeleton.frontier.achievements`, derives monotonic evidence
from catches, then delegates qualification/claim semantics to that existing
canonical kernel.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from skeleton.frontier.achievements import (
    AchievementRequirement,
    AchievementSpec,
    AchievementState,
    unlock_qualified,
)


DEFAULT_REQUIREMENT_STAGE_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        "reef_species": "coral_reef",
        "ancient_lake_species": "ancient_lake",
        "mangrove_species": "mangrove_forest",
    }
)

# Source catalog requirement names do not always match the stats emitted by the
# source recorder. Keep those compatibility bindings explicit instead of
# silently inventing generic aliases from names.
DEFAULT_REQUIREMENT_COUNT_ALIASES: Mapping[str, str] = MappingProxyType(
    {
        "lake_catches": "freshwater_lake_catches",
        "arctic_catches": "arctic_ocean_catches",
    }
)


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _token(value: object, field_name: str) -> str:
    token = _text(value, field_name).lower()
    if token != value:
        raise ValueError(f"{field_name} must be lowercase and normalized")
    return token


def _nonnegative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must not be negative")
    return value


def _positive_int(value: object, field_name: str) -> int:
    value = _nonnegative_int(value, field_name)
    if value < 1:
        raise ValueError(f"{field_name} must be positive")
    return value


def _string_set(values: Iterable[str], field_name: str) -> frozenset[str]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} must be an iterable of strings")
    result: set[str] = set()
    for value in values:
        result.add(_token(value, f"{field_name} entry"))
    return frozenset(result)


def _count_map(values: Mapping[str, int], field_name: str) -> Mapping[str, int]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    normalized: dict[str, int] = {}
    for raw_key, raw_value in values.items():
        key = _token(raw_key, f"{field_name} key")
        normalized[key] = _nonnegative_int(raw_value, f"{field_name}[{key!r}]")
    return MappingProxyType(normalized)


def _set_map(
    values: Mapping[str, Iterable[str]],
    field_name: str,
) -> Mapping[str, frozenset[str]]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    normalized: dict[str, frozenset[str]] = {}
    for raw_key, raw_values in values.items():
        key = _token(raw_key, f"{field_name} key")
        normalized[key] = _string_set(raw_values, f"{field_name}[{key!r}]")
    return MappingProxyType(normalized)


@dataclass(frozen=True, slots=True)
class BiotopeCatchEvidence:
    counts: Mapping[str, int]
    species_by_stage: Mapping[str, frozenset[str]]
    max_size_by_biotope: Mapping[str, int]
    fish_ids: frozenset[str]
    biotopes_fished: frozenset[str]
    trophy_biotopes: frozenset[str]
    legendary_biotopes: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "counts", _count_map(self.counts, "catch evidence counts"))
        object.__setattr__(
            self,
            "species_by_stage",
            _set_map(self.species_by_stage, "catch evidence species_by_stage"),
        )
        object.__setattr__(
            self,
            "max_size_by_biotope",
            _count_map(self.max_size_by_biotope, "catch evidence max_size_by_biotope"),
        )
        object.__setattr__(self, "fish_ids", _string_set(self.fish_ids, "catch evidence fish_ids"))
        object.__setattr__(
            self,
            "biotopes_fished",
            _string_set(self.biotopes_fished, "catch evidence biotopes_fished"),
        )
        object.__setattr__(
            self,
            "trophy_biotopes",
            _string_set(self.trophy_biotopes, "catch evidence trophy_biotopes"),
        )
        object.__setattr__(
            self,
            "legendary_biotopes",
            _string_set(self.legendary_biotopes, "catch evidence legendary_biotopes"),
        )
        known_biotopes = set(self.biotopes_fished)
        if not set(self.max_size_by_biotope).issubset(known_biotopes):
            raise ValueError("max-size evidence may only reference fished biotopes")
        if not self.trophy_biotopes.issubset(known_biotopes):
            raise ValueError("trophy evidence may only reference fished biotopes")
        if not self.legendary_biotopes.issubset(known_biotopes):
            raise ValueError("legendary evidence may only reference fished biotopes")


def empty_biotope_catch_evidence() -> BiotopeCatchEvidence:
    return BiotopeCatchEvidence(
        counts={},
        species_by_stage={},
        max_size_by_biotope={},
        fish_ids=frozenset(),
        biotopes_fished=frozenset(),
        trophy_biotopes=frozenset(),
        legendary_biotopes=frozenset(),
    )


def biotope_achievement_from_record(record: Mapping[str, Any]) -> AchievementSpec:
    """Normalize the nested-reward/size-aware source achievement shape."""

    if not isinstance(record, Mapping):
        raise TypeError("biotope achievement record must be a mapping")
    achievement_id = _token(record.get("id"), "biotope achievement id")
    name = _text(record.get("name"), "biotope achievement name")
    category = _token(record.get("category"), "biotope achievement category")
    biotope = _token(record.get("biotope"), "biotope achievement biotope")

    raw_requirement = record.get("requirement")
    if not isinstance(raw_requirement, Mapping):
        raise TypeError("biotope achievement requirement must be a mapping")
    kind = _token(raw_requirement.get("type"), "biotope achievement requirement type")
    has_count = "count" in raw_requirement
    has_size = "size" in raw_requirement
    if has_count == has_size:
        raise ValueError("biotope achievement requirement must define exactly one of count or size")
    threshold_key = "count" if has_count else "size"
    threshold = _positive_int(
        raw_requirement.get(threshold_key),
        f"biotope achievement requirement {threshold_key}",
    )
    qualifiers = {
        _token(key, "biotope achievement requirement qualifier key"): value
        for key, value in raw_requirement.items()
        if key not in {"type", threshold_key}
    }
    if "each" in qualifiers:
        qualifiers["each"] = _positive_int(
            qualifiers["each"], "biotope achievement requirement each"
        )

    raw_rewards = record.get("rewards", {})
    if not isinstance(raw_rewards, Mapping):
        raise TypeError("biotope achievement rewards must be a mapping")
    rewards: dict[str, Any] = {}
    for currency in ("xp", "coins", "gems"):
        if currency in raw_rewards:
            rewards[currency] = _nonnegative_int(
                raw_rewards[currency], f"biotope achievement reward {currency}"
            )
    if "title" in raw_rewards:
        rewards["title"] = _text(raw_rewards["title"], "biotope achievement reward title")

    return AchievementSpec(
        id=achievement_id,
        name=name,
        description=str(record.get("description") or "").strip(),
        category=category,
        icon=str(record.get("icon") or "").strip(),
        requirement=AchievementRequirement(kind=kind, count=threshold),
        rewards=MappingProxyType(rewards),
        metadata=MappingProxyType(
            {
                "biotope": biotope,
                "requirement_threshold_kind": threshold_key,
                "requirement_qualifiers": MappingProxyType(qualifiers),
            }
        ),
    )


def record_biotope_catch(
    evidence: BiotopeCatchEvidence,
    *,
    fish_id: str,
    biotope_id: str,
    stage_id: str,
    size: int,
    rarity: str,
    is_trophy: bool = False,
    family_tokens: Sequence[str] | None = None,
) -> BiotopeCatchEvidence:
    """Record monotonic catch evidence without persistence or catalog access."""

    if not isinstance(evidence, BiotopeCatchEvidence):
        raise TypeError("evidence must be BiotopeCatchEvidence")
    fish = _token(fish_id, "caught fish id")
    biotope = _token(biotope_id, "caught fish biotope id")
    stage = _token(stage_id, "caught fish stage id")
    rarity_token = _token(rarity, "caught fish rarity")
    numeric_size = _nonnegative_int(size, "caught fish size")
    if not isinstance(is_trophy, bool):
        raise TypeError("is_trophy must be a boolean")

    counts = dict(evidence.counts)
    emitted_count_keys: set[str] = set()

    def increment(key: str) -> None:
        if key in emitted_count_keys:
            return
        emitted_count_keys.add(key)
        counts[key] = counts.get(key, 0) + 1

    increment(f"{biotope}_catches")
    increment(f"{stage}_catches")
    increment(f"{rarity_token}_catches")
    increment(f"{stage}_{rarity_token}")
    increment(f"{biotope}_{rarity_token}")

    if family_tokens is None:
        families = tuple(dict.fromkeys(part for part in fish.split("_") if part))
    else:
        if isinstance(family_tokens, (str, bytes)):
            raise TypeError("family_tokens must be a sequence of strings")
        families = tuple(
            dict.fromkeys(_token(value, "caught fish family token") for value in family_tokens)
        )

    for family in families:
        increment(f"{family}_catches")

    species_by_stage = {key: set(values) for key, values in evidence.species_by_stage.items()}
    species_by_stage.setdefault(stage, set()).add(fish)

    max_size = dict(evidence.max_size_by_biotope)
    max_size[biotope] = max(max_size.get(biotope, 0), numeric_size)
    fish_ids = set(evidence.fish_ids)
    fish_ids.add(fish)
    biotopes = set(evidence.biotopes_fished)
    biotopes.add(biotope)
    trophies = set(evidence.trophy_biotopes)
    if is_trophy:
        trophies.add(biotope)
    legendaries = set(evidence.legendary_biotopes)
    if rarity_token == "legendary":
        legendaries.add(biotope)

    return BiotopeCatchEvidence(
        counts=counts,
        species_by_stage={key: frozenset(values) for key, values in species_by_stage.items()},
        max_size_by_biotope=max_size,
        fish_ids=frozenset(fish_ids),
        biotopes_fished=frozenset(biotopes),
        trophy_biotopes=frozenset(trophies),
        legendary_biotopes=frozenset(legendaries),
    )


def _qualifiers(achievement: AchievementSpec) -> Mapping[str, Any]:
    raw = achievement.metadata.get("requirement_qualifiers", {})
    if not isinstance(raw, Mapping):
        raise TypeError("achievement requirement_qualifiers metadata must be a mapping")
    return raw


def biotope_requirement_value(
    achievement: AchievementSpec,
    evidence: BiotopeCatchEvidence,
    *,
    stage_aliases: Mapping[str, str] = DEFAULT_REQUIREMENT_STAGE_ALIASES,
    count_aliases: Mapping[str, str] = DEFAULT_REQUIREMENT_COUNT_ALIASES,
) -> int:
    """Resolve one source requirement from derived catch evidence."""

    kind = achievement.requirement.kind
    if kind == "biotopes_fished":
        return len(evidence.biotopes_fished)
    if kind == "biotopes_mastered":
        each = _positive_int(_qualifiers(achievement).get("each"), "biotopes_mastered each")
        return sum(
            evidence.counts.get(f"{biotope}_catches", 0) >= each
            for biotope in evidence.biotopes_fished
        )
    if kind == "all_biotope_fish":
        return len(evidence.fish_ids)
    if kind == "trophy_biotopes":
        return len(evidence.trophy_biotopes)
    if kind == "legendary_per_biotope":
        return len(evidence.legendary_biotopes)

    if kind in stage_aliases:
        stage = _token(stage_aliases[kind], f"stage alias for {kind}")
        return len(evidence.species_by_stage.get(stage, frozenset()))

    if kind.endswith("_trophy"):
        biotope = _token(achievement.metadata.get("biotope"), "achievement biotope metadata")
        return evidence.max_size_by_biotope.get(biotope, 0)

    if kind in count_aliases:
        alias = _token(count_aliases[kind], f"count alias for {kind}")
        return evidence.counts.get(alias, 0)

    return evidence.counts.get(kind, 0)


def synchronize_biotope_achievement_state(
    achievements: Sequence[AchievementSpec],
    state: AchievementState,
    evidence: BiotopeCatchEvidence,
    *,
    stage_aliases: Mapping[str, str] = DEFAULT_REQUIREMENT_STAGE_ALIASES,
    count_aliases: Mapping[str, str] = DEFAULT_REQUIREMENT_COUNT_ALIASES,
) -> tuple[AchievementState, tuple[AchievementSpec, ...]]:
    """Merge derived evidence into canonical stats, then use the existing engine."""

    if isinstance(achievements, (str, bytes)):
        raise TypeError("achievements must be a sequence of AchievementSpec values")
    stats = dict(state.stats)
    for achievement in achievements:
        if not isinstance(achievement, AchievementSpec):
            raise TypeError("achievements must contain AchievementSpec values")
        derived = biotope_requirement_value(
            achievement,
            evidence,
            stage_aliases=stage_aliases,
            count_aliases=count_aliases,
        )
        kind = achievement.requirement.kind
        stats[kind] = max(stats.get(kind, 0), derived)

    synchronized = AchievementState(
        stats=stats,
        unlocked=state.unlocked,
        claimed=state.claimed,
    )
    return unlock_qualified(achievements, synchronized)