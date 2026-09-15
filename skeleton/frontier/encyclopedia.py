"""Dependency-free encyclopedia and collection policy.

Promoted once from the byte-identical Lorebuffa/Openworld
``backend/encyclopedia_routes.py`` blob
``e842d3697187503b1e1da2df3563d797777c6bfb``.

The source repositories remain authoritative for the large fish catalog,
presentation copy, FastAPI routes and MongoDB persistence.  This module keeps
only portable collection semantics and hardens mutation boundaries:

* discovery level is enforced by the mutation path rather than UI metadata;
* catch size is positive and catalog-bounded;
* first-caught identity is immutable after discovery;
* discovered species and per-species stats have exact coverage;
* catalog/state digests make persistence boundaries tamper-evident;
* collection and fishing summaries use deterministic tie-breaking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence

from skeleton.frontier.contracts import stable_content_digest


DEFAULT_RARITIES = ("common", "uncommon", "rare", "epic", "legendary")


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value or value.strip() != value:
        raise ValueError(f"{field_name} must be non-empty and normalized")
    return value


def _token(value: object, field_name: str) -> str:
    text = _text(value, field_name)
    normalized = text.lower()
    if normalized != text:
        raise ValueError(f"{field_name} must be lowercase and normalized")
    return normalized


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


def _aware(value: object, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _id_set(values: Iterable[str], field_name: str) -> frozenset[str]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{field_name} must be an iterable of strings")
    normalized: set[str] = set()
    for raw in values:
        value = _token(raw, f"{field_name} entry")
        if value in normalized:
            raise ValueError(f"duplicate {field_name} entry: {value}")
        normalized.add(value)
    return frozenset(normalized)


@dataclass(frozen=True, slots=True)
class FishSpeciesSpec:
    id: str
    rarity: str
    discovery_level: int
    min_size: int
    max_size: int

    def __post_init__(self) -> None:
        species_id = _token(self.id, "fish species id")
        rarity = _token(self.rarity, "fish rarity")
        level = _positive_int(self.discovery_level, "fish discovery_level")
        minimum = _positive_int(self.min_size, "fish min_size")
        maximum = _positive_int(self.max_size, "fish max_size")
        if maximum < minimum:
            raise ValueError("fish max_size must be >= min_size")
        object.__setattr__(self, "id", species_id)
        object.__setattr__(self, "rarity", rarity)
        object.__setattr__(self, "discovery_level", level)
        object.__setattr__(self, "min_size", minimum)
        object.__setattr__(self, "max_size", maximum)


def species_from_record(record: Mapping[str, object]) -> FishSpeciesSpec:
    """Normalize the portable policy fields from one source catalog record."""

    if not isinstance(record, Mapping):
        raise TypeError("fish species record must be a mapping")
    size_range = record.get("size_range")
    if not isinstance(size_range, Mapping):
        raise TypeError("fish size_range must be a mapping")
    return FishSpeciesSpec(
        id=_token(record.get("id"), "fish species id"),
        rarity=_token(record.get("rarity"), "fish rarity"),
        discovery_level=_positive_int(
            record.get("discovery_level"), "fish discovery_level"
        ),
        min_size=_positive_int(size_range.get("min"), "fish min_size"),
        max_size=_positive_int(size_range.get("max"), "fish max_size"),
    )


def _catalog(specs: Sequence[FishSpeciesSpec]) -> Mapping[str, FishSpeciesSpec]:
    if isinstance(specs, (str, bytes)):
        raise TypeError("fish catalog must be a sequence of FishSpeciesSpec")
    result: dict[str, FishSpeciesSpec] = {}
    for spec in specs:
        if not isinstance(spec, FishSpeciesSpec):
            raise TypeError("fish catalog must contain FishSpeciesSpec values")
        if spec.id in result:
            raise ValueError(f"duplicate fish species id: {spec.id}")
        result[spec.id] = spec
    return MappingProxyType(result)


def catalog_digest(specs: Sequence[FishSpeciesSpec]) -> str:
    catalog = _catalog(specs)
    return stable_content_digest(
        [
            {
                "id": spec.id,
                "rarity": spec.rarity,
                "discovery_level": spec.discovery_level,
                "min_size": spec.min_size,
                "max_size": spec.max_size,
            }
            for spec in sorted(catalog.values(), key=lambda item: item.id)
        ]
    )


@dataclass(frozen=True, slots=True)
class FishCatchStats:
    caught: int
    largest: int
    smallest: int
    first_caught: datetime

    def __post_init__(self) -> None:
        caught = _positive_int(self.caught, "fish caught count")
        largest = _positive_int(self.largest, "fish largest size")
        smallest = _positive_int(self.smallest, "fish smallest size")
        if largest < smallest:
            raise ValueError("fish largest size must be >= smallest size")
        first = _aware(self.first_caught, "fish first_caught")
        object.__setattr__(self, "caught", caught)
        object.__setattr__(self, "largest", largest)
        object.__setattr__(self, "smallest", smallest)
        object.__setattr__(self, "first_caught", first)


@dataclass(frozen=True, slots=True)
class CollectionState:
    discovered_species: frozenset[str] = frozenset()
    fish_stats: Mapping[str, FishCatchStats] = field(default_factory=dict)

    def __post_init__(self) -> None:
        discovered = _id_set(self.discovered_species, "discovered species")
        if not isinstance(self.fish_stats, Mapping):
            raise TypeError("fish_stats must be a mapping")
        stats: dict[str, FishCatchStats] = {}
        for raw_key, value in self.fish_stats.items():
            key = _token(raw_key, "fish_stats key")
            if key in stats:
                raise ValueError(f"duplicate fish_stats key: {key}")
            if not isinstance(value, FishCatchStats):
                raise TypeError("fish_stats values must be FishCatchStats")
            stats[key] = value
        if set(stats) != set(discovered):
            raise ValueError(
                "fish_stats must have exact coverage for discovered species"
            )
        object.__setattr__(self, "discovered_species", discovered)
        object.__setattr__(self, "fish_stats", MappingProxyType(stats))


def collection_state_digest(state: CollectionState) -> str:
    if not isinstance(state, CollectionState):
        raise TypeError("state must be CollectionState")
    return stable_content_digest(
        {
            "discovered_species": sorted(state.discovered_species),
            "fish_stats": {
                species_id: {
                    "caught": stats.caught,
                    "largest": stats.largest,
                    "smallest": stats.smallest,
                    "first_caught": stats.first_caught.isoformat(),
                }
                for species_id, stats in sorted(state.fish_stats.items())
            },
        }
    )


def validate_collection_against_catalog(
    state: CollectionState,
    specs: Sequence[FishSpeciesSpec],
) -> None:
    if not isinstance(state, CollectionState):
        raise TypeError("state must be CollectionState")
    catalog = _catalog(specs)
    unknown = set(state.discovered_species).difference(catalog)
    if unknown:
        raise ValueError(
            "collection contains species absent from catalog: "
            + ", ".join(sorted(unknown))
        )
    for species_id, stats in state.fish_stats.items():
        spec = catalog[species_id]
        if not spec.min_size <= stats.smallest <= spec.max_size:
            raise ValueError(f"stored smallest size is invalid for {species_id}")
        if not spec.min_size <= stats.largest <= spec.max_size:
            raise ValueError(f"stored largest size is invalid for {species_id}")


@dataclass(frozen=True, slots=True)
class CollectionCatchPlan:
    state: CollectionState
    species_id: str
    is_new_discovery: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "species_id", _token(self.species_id, "catch species_id"))
        if not isinstance(self.is_new_discovery, bool):
            raise TypeError("is_new_discovery must be a boolean")


def record_collection_catch(
    state: CollectionState,
    spec: FishSpeciesSpec,
    *,
    player_level: int,
    size: int,
    occurred_at: datetime,
) -> CollectionCatchPlan:
    """Record one catalog-bound catch as an immutable collection transition."""

    if not isinstance(state, CollectionState):
        raise TypeError("state must be CollectionState")
    if not isinstance(spec, FishSpeciesSpec):
        raise TypeError("spec must be FishSpeciesSpec")
    level = _positive_int(player_level, "player level")
    catch_size = _positive_int(size, "catch size")
    occurred = _aware(occurred_at, "catch occurred_at")
    if level < spec.discovery_level:
        raise PermissionError(
            f"fish species requires discovery level {spec.discovery_level}"
        )
    if not spec.min_size <= catch_size <= spec.max_size:
        raise ValueError(
            f"catch size for {spec.id} must be between {spec.min_size} and {spec.max_size}"
        )

    discovered = set(state.discovered_species)
    stats_map = dict(state.fish_stats)
    is_new = spec.id not in discovered
    if is_new:
        discovered.add(spec.id)
        stats_map[spec.id] = FishCatchStats(
            caught=1,
            largest=catch_size,
            smallest=catch_size,
            first_caught=occurred,
        )
    else:
        previous = stats_map[spec.id]
        stats_map[spec.id] = FishCatchStats(
            caught=previous.caught + 1,
            largest=max(previous.largest, catch_size),
            smallest=min(previous.smallest, catch_size),
            first_caught=previous.first_caught,
        )
    return CollectionCatchPlan(
        state=CollectionState(
            discovered_species=frozenset(discovered),
            fish_stats=stats_map,
        ),
        species_id=spec.id,
        is_new_discovery=is_new,
    )


def discoverable_species(
    specs: Sequence[FishSpeciesSpec],
    *,
    player_level: int,
    state: CollectionState | None = None,
    include_discovered: bool = True,
) -> tuple[FishSpeciesSpec, ...]:
    level = _positive_int(player_level, "player level")
    if not isinstance(include_discovered, bool):
        raise TypeError("include_discovered must be a boolean")
    catalog = _catalog(specs)
    discovered = frozenset()
    if state is not None:
        if not isinstance(state, CollectionState):
            raise TypeError("state must be CollectionState")
        validate_collection_against_catalog(state, specs)
        discovered = state.discovered_species
    return tuple(
        spec
        for spec in sorted(
            catalog.values(), key=lambda item: (item.discovery_level, item.id)
        )
        if spec.discovery_level <= level
        and (include_discovered or spec.id not in discovered)
    )


@dataclass(frozen=True, slots=True)
class RarityProgress:
    rarity: str
    total: int
    discovered: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "rarity", _token(self.rarity, "rarity progress rarity"))
        total = _nonnegative_int(self.total, "rarity progress total")
        discovered = _nonnegative_int(self.discovered, "rarity progress discovered")
        if discovered > total:
            raise ValueError("rarity discovered count cannot exceed total")
        object.__setattr__(self, "total", total)
        object.__setattr__(self, "discovered", discovered)


@dataclass(frozen=True, slots=True)
class CollectionProgress:
    total: int
    discovered: int
    completion_bps: int
    by_rarity: tuple[RarityProgress, ...]

    @property
    def complete(self) -> bool:
        return self.total > 0 and self.discovered == self.total


def collection_progress(
    state: CollectionState,
    specs: Sequence[FishSpeciesSpec],
    *,
    rarity_order: Sequence[str] = DEFAULT_RARITIES,
) -> CollectionProgress:
    validate_collection_against_catalog(state, specs)
    catalog = _catalog(specs)
    order: list[str] = []
    seen: set[str] = set()
    if isinstance(rarity_order, (str, bytes)):
        raise TypeError("rarity_order must be a sequence")
    for raw in rarity_order:
        rarity = _token(raw, "rarity_order entry")
        if rarity not in seen:
            seen.add(rarity)
            order.append(rarity)
    for rarity in sorted({spec.rarity for spec in catalog.values()}):
        if rarity not in seen:
            seen.add(rarity)
            order.append(rarity)

    total = len(catalog)
    discovered = len(state.discovered_species)
    completion_bps = 0 if total == 0 else discovered * 10_000 // total
    rarity_rows: list[RarityProgress] = []
    for rarity in order:
        species_ids = {
            spec.id for spec in catalog.values() if spec.rarity == rarity
        }
        rarity_rows.append(
            RarityProgress(
                rarity=rarity,
                total=len(species_ids),
                discovered=len(species_ids.intersection(state.discovered_species)),
            )
        )
    return CollectionProgress(
        total=total,
        discovered=discovered,
        completion_bps=completion_bps,
        by_rarity=tuple(rarity_rows),
    )


@dataclass(frozen=True, slots=True)
class FishingStatistics:
    total_fish_caught: int
    unique_species_discovered: int
    largest_species_id: str | None
    largest_size: int
    most_caught_species_id: str | None
    most_caught_count: int
    catches_by_rarity: Mapping[str, int]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "total_fish_caught",
            _nonnegative_int(self.total_fish_caught, "total_fish_caught"),
        )
        object.__setattr__(
            self,
            "unique_species_discovered",
            _nonnegative_int(
                self.unique_species_discovered, "unique_species_discovered"
            ),
        )
        if self.largest_species_id is not None:
            object.__setattr__(
                self,
                "largest_species_id",
                _token(self.largest_species_id, "largest_species_id"),
            )
        object.__setattr__(
            self, "largest_size", _nonnegative_int(self.largest_size, "largest_size")
        )
        if self.most_caught_species_id is not None:
            object.__setattr__(
                self,
                "most_caught_species_id",
                _token(self.most_caught_species_id, "most_caught_species_id"),
            )
        object.__setattr__(
            self,
            "most_caught_count",
            _nonnegative_int(self.most_caught_count, "most_caught_count"),
        )
        if not isinstance(self.catches_by_rarity, Mapping):
            raise TypeError("catches_by_rarity must be a mapping")
        rarity_counts: dict[str, int] = {}
        for raw_key, raw_value in self.catches_by_rarity.items():
            key = _token(raw_key, "catches_by_rarity key")
            rarity_counts[key] = _nonnegative_int(
                raw_value, f"catches_by_rarity[{key!r}]"
            )
        object.__setattr__(
            self, "catches_by_rarity", MappingProxyType(rarity_counts)
        )


def fishing_statistics(
    state: CollectionState,
    specs: Sequence[FishSpeciesSpec],
) -> FishingStatistics:
    validate_collection_against_catalog(state, specs)
    catalog = _catalog(specs)
    total_caught = sum(stats.caught for stats in state.fish_stats.values())

    largest_species_id: str | None = None
    largest_size = 0
    most_caught_species_id: str | None = None
    most_caught_count = 0
    rarity_counts: dict[str, int] = {}

    for species_id in sorted(state.fish_stats):
        stats = state.fish_stats[species_id]
        spec = catalog[species_id]
        rarity_counts[spec.rarity] = rarity_counts.get(spec.rarity, 0) + stats.caught
        if stats.largest > largest_size:
            largest_size = stats.largest
            largest_species_id = species_id
        elif stats.largest == largest_size and largest_species_id is not None:
            largest_species_id = min(largest_species_id, species_id)
        if stats.caught > most_caught_count:
            most_caught_count = stats.caught
            most_caught_species_id = species_id
        elif stats.caught == most_caught_count and most_caught_species_id is not None:
            most_caught_species_id = min(most_caught_species_id, species_id)

    return FishingStatistics(
        total_fish_caught=total_caught,
        unique_species_discovered=len(state.discovered_species),
        largest_species_id=largest_species_id,
        largest_size=largest_size,
        most_caught_species_id=most_caught_species_id,
        most_caught_count=most_caught_count,
        catches_by_rarity=rarity_counts,
    )
