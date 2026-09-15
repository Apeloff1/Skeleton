"""Pure fish-encyclopedia collection policy from exact-shared source lineage.

Lorebuffa and Openworld share ``backend/encyclopedia_routes.py`` blob
``e842d3697187503b1e1da2df3563d797777c6bfb``. The source fish database,
FastAPI routes and MongoDB persistence remain source-owned. This module promotes
only portable collection state, catch aggregation, masking and summary policy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from types import MappingProxyType
from typing import Any, Iterable, Mapping


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


def _positive_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
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


def _id_set(values: Iterable[str], field_name: str) -> frozenset[str]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} must be an iterable of strings")
    result: set[str] = set()
    for raw_value in values:
        value = _text(raw_value, f"{field_name} entry")
        if value in result:
            raise ValueError(f"duplicate {field_name} entry: {value}")
        result.add(value)
    return frozenset(result)


def _stats_payload(stats: FishDiscoveryStats | None) -> Mapping[str, Any]:
    if stats is None:
        return {}
    return {
        "caught": stats.caught,
        "largest": stats.largest,
        "smallest": stats.smallest,
        "first_caught": stats.first_caught.isoformat(),
    }


@dataclass(frozen=True, slots=True)
class FishDiscoveryStats:
    caught: int
    largest: float
    smallest: float
    first_caught: datetime

    def __post_init__(self) -> None:
        caught = _positive_int(self.caught, "fish caught count")
        largest = _positive_number(self.largest, "largest fish size")
        smallest = _positive_number(self.smallest, "smallest fish size")
        if smallest > largest:
            raise ValueError("smallest fish size cannot exceed largest fish size")
        first_caught = _aware(self.first_caught, "fish first_caught")
        object.__setattr__(self, "caught", caught)
        object.__setattr__(self, "largest", largest)
        object.__setattr__(self, "smallest", smallest)
        object.__setattr__(self, "first_caught", first_caught)


@dataclass(frozen=True, slots=True)
class FishCollectionState:
    discovered_fish: frozenset[str] = frozenset()
    fish_stats: Mapping[str, FishDiscoveryStats] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __post_init__(self) -> None:
        discovered = _id_set(self.discovered_fish, "discovered fish")
        if not isinstance(self.fish_stats, Mapping):
            raise TypeError("fish_stats must be a mapping")

        normalized_stats: dict[str, FishDiscoveryStats] = {}
        for raw_fish_id, raw_stats in self.fish_stats.items():
            fish_id = _text(raw_fish_id, "fish_stats key")
            if fish_id in normalized_stats:
                raise ValueError(f"duplicate fish_stats key: {fish_id}")
            if not isinstance(raw_stats, FishDiscoveryStats):
                raise TypeError("fish_stats values must be FishDiscoveryStats")
            normalized_stats[fish_id] = raw_stats

        if set(normalized_stats) != set(discovered):
            raise ValueError(
                "fish_stats keys must exactly match discovered_fish identities"
            )
        object.__setattr__(self, "discovered_fish", discovered)
        object.__setattr__(
            self,
            "fish_stats",
            MappingProxyType(dict(sorted(normalized_stats.items()))),
        )


@dataclass(frozen=True, slots=True)
class FishCatchPlan:
    collection: FishCollectionState
    fish_id: str
    is_new_discovery: bool
    stats: FishDiscoveryStats


@dataclass(frozen=True, slots=True)
class FishCollectionSummary:
    total_fish_caught: int
    unique_species_discovered: int
    largest_catch_id: str | None
    largest_catch_size: float
    most_caught_id: str | None
    most_caught_count: int


def empty_collection() -> FishCollectionState:
    return FishCollectionState()


def record_fish_catch(
    collection: FishCollectionState,
    *,
    fish_id: str,
    size: int | float,
    occurred_at: datetime,
) -> FishCatchPlan:
    """Record one catch without persistence or catalog ownership.

    ``first_caught`` uses the earliest observed timestamp rather than whichever
    event happened to be processed first. This makes replay/out-of-order recovery
    converge to the same collection state.
    """

    if not isinstance(collection, FishCollectionState):
        raise TypeError("collection must be FishCollectionState")
    identity = _text(fish_id, "fish_id")
    measured_size = _positive_number(size, "fish size")
    occurred = _aware(occurred_at, "fish catch occurred_at")

    existing = collection.fish_stats.get(identity)
    is_new = existing is None
    if existing is None:
        stats = FishDiscoveryStats(
            caught=1,
            largest=measured_size,
            smallest=measured_size,
            first_caught=occurred,
        )
    else:
        stats = FishDiscoveryStats(
            caught=existing.caught + 1,
            largest=max(existing.largest, measured_size),
            smallest=min(existing.smallest, measured_size),
            first_caught=min(existing.first_caught, occurred),
        )

    next_stats = dict(collection.fish_stats)
    next_stats[identity] = stats
    next_collection = FishCollectionState(
        discovered_fish=collection.discovered_fish | {identity},
        fish_stats=next_stats,
    )
    return FishCatchPlan(
        collection=next_collection,
        fish_id=identity,
        is_new_discovery=is_new,
        stats=stats,
    )


def collection_completion_percent(
    collection: FishCollectionState,
    catalog_fish_ids: Iterable[str],
) -> float:
    """Calculate completion against caller-owned catalog identities."""

    if not isinstance(collection, FishCollectionState):
        raise TypeError("collection must be FishCollectionState")
    catalog = _id_set(catalog_fish_ids, "catalog fish")
    unknown = collection.discovered_fish.difference(catalog)
    if unknown:
        raise ValueError(
            "collection contains fish absent from supplied catalog: "
            + ", ".join(sorted(unknown))
        )
    if not catalog:
        return 0.0
    return round((len(collection.discovered_fish) / len(catalog)) * 100, 1)


def project_fish_entry(
    record: Mapping[str, Any],
    collection: FishCollectionState,
    *,
    player_level: int,
) -> Mapping[str, Any]:
    """Project one external catalog entry with source-compatible masking."""

    if not isinstance(record, Mapping):
        raise TypeError("fish encyclopedia record must be a mapping")
    if not isinstance(collection, FishCollectionState):
        raise TypeError("collection must be FishCollectionState")
    level = _positive_int(player_level, "player_level")
    fish_id = _text(record.get("id"), "fish encyclopedia id")
    discovery_level = _positive_int(
        record.get("discovery_level"), "fish discovery_level"
    )

    name = record.get("name")
    description = record.get("description")
    facts = record.get("facts", ())
    if not isinstance(name, str):
        raise TypeError("fish encyclopedia name must be a string")
    if not isinstance(description, str):
        raise TypeError("fish encyclopedia description must be a string")
    if isinstance(facts, (str, bytes)) or not isinstance(facts, Iterable):
        raise TypeError("fish encyclopedia facts must be an iterable")
    normalized_facts: list[str] = []
    for fact in facts:
        normalized_facts.append(_text(fact, "fish encyclopedia fact"))

    discovered = fish_id in collection.discovered_fish
    can_discover = level >= discovery_level
    projected = dict(record)
    projected["discovered"] = discovered
    projected["can_discover"] = can_discover
    projected["stats"] = dict(_stats_payload(collection.fish_stats.get(fish_id)))
    if not discovered:
        projected["description"] = "???"
        projected["facts"] = []
        if not can_discover:
            projected["name"] = "???"
    else:
        projected["facts"] = normalized_facts
    return projected


def collection_summary(collection: FishCollectionState) -> FishCollectionSummary:
    """Return deterministic source-compatible aggregate catch statistics."""

    if not isinstance(collection, FishCollectionState):
        raise TypeError("collection must be FishCollectionState")
    total_caught = sum(stats.caught for stats in collection.fish_stats.values())

    largest_id: str | None = None
    largest_size = 0.0
    most_caught_id: str | None = None
    most_caught_count = 0
    for fish_id in sorted(collection.fish_stats):
        stats = collection.fish_stats[fish_id]
        if stats.largest > largest_size:
            largest_id = fish_id
            largest_size = stats.largest
        if stats.caught > most_caught_count:
            most_caught_id = fish_id
            most_caught_count = stats.caught

    return FishCollectionSummary(
        total_fish_caught=total_caught,
        unique_species_discovered=len(collection.discovered_fish),
        largest_catch_id=largest_id,
        largest_catch_size=largest_size,
        most_caught_id=most_caught_id,
        most_caught_count=most_caught_count,
    )


def rarity_catch_counts(
    collection: FishCollectionState,
    rarity_by_fish: Mapping[str, str],
) -> Mapping[str, int]:
    """Aggregate caught counts using a caller-owned fish→rarity mapping."""

    if not isinstance(collection, FishCollectionState):
        raise TypeError("collection must be FishCollectionState")
    if not isinstance(rarity_by_fish, Mapping):
        raise TypeError("rarity_by_fish must be a mapping")

    normalized_rarity: dict[str, str] = {}
    for raw_fish_id, raw_rarity in rarity_by_fish.items():
        fish_id = _text(raw_fish_id, "rarity fish id")
        rarity = _text(raw_rarity, f"rarity for {fish_id}").lower()
        normalized_rarity[fish_id] = rarity

    missing = collection.discovered_fish.difference(normalized_rarity)
    if missing:
        raise ValueError(
            "rarity mapping missing discovered fish: " + ", ".join(sorted(missing))
        )

    counts: dict[str, int] = {}
    for fish_id, stats in collection.fish_stats.items():
        rarity = normalized_rarity[fish_id]
        counts[rarity] = counts.get(rarity, 0) + stats.caught
    return MappingProxyType(dict(sorted(counts.items())))
