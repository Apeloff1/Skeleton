"""Pure world policy selectively promoted from Lorebuffa/Openworld.

Lineage: ``backend/world_map.py`` is the same blob in both repositories:
``a32259d514710c3e87d7ce5fe42f6fb73e63ca1b``.

Only portable policy lives here. FastAPI routes, Motor/MongoDB persistence and
the source world catalog remain in their source applications. Randomness,
identity and time are injected so the promoted behavior is deterministic under
test.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class WorldBounds:
    x: int
    y: int
    width: int
    height: int

    @property
    def max_x(self) -> int:
        return self.x + self.width

    @property
    def max_y(self) -> int:
        return self.y + self.height

    def contains(self, point: tuple[float, float]) -> bool:
        """Return whether ``point`` is inside these half-open bounds.

        Region lookup intentionally uses half-open rectangles so adjacent
        source regions do not both own a coordinate on their shared edge.
        """

        x, y = point
        return self.x <= x < self.max_x and self.y <= y < self.max_y


@dataclass(frozen=True, slots=True)
class WorldRegion:
    id: str
    name: str
    difficulty: int
    bounds: WorldBounds
    dangers: tuple[str, ...] = ()
    points_of_interest: tuple[Mapping[str, Any], ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


def _string_sequence(value: Any, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"{field_name} must be a sequence")
    return tuple(
        text
        for item in value
        if (text := str(item).strip().lower())
    )


def _point_records(value: Any) -> tuple[Mapping[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError("points_of_interest must be a sequence")

    points: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise TypeError(f"points_of_interest[{index}] must be a mapping")
        points.append(dict(item))
    return tuple(points)


def _validate_point(point: tuple[float, float], *, name: str) -> None:
    if len(point) != 2:
        raise ValueError(f"{name} must contain exactly two coordinates")
    try:
        finite = all(math.isfinite(float(value)) for value in point)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain finite numeric coordinates") from exc
    if not finite:
        raise ValueError(f"{name} must contain finite numeric coordinates")


def region_from_record(record: Mapping[str, Any]) -> WorldRegion:
    """Normalize a source world-region record without importing its catalog."""

    region_id = str(record.get("id") or "").strip()
    name = str(record.get("name") or "").strip()
    if not region_id or not name:
        raise ValueError("world region requires non-empty id and name")

    raw_bounds = record.get("bounds")
    if not isinstance(raw_bounds, Mapping):
        raise ValueError("world region requires bounds")
    try:
        bounds = WorldBounds(
            x=int(raw_bounds["x"]),
            y=int(raw_bounds["y"]),
            width=int(raw_bounds["width"]),
            height=int(raw_bounds["height"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("world region bounds require x/y/width/height integers") from exc
    if bounds.width < 0 or bounds.height < 0:
        raise ValueError("world region bounds must not be negative")

    try:
        difficulty = int(record.get("difficulty", 1))
    except (TypeError, ValueError) as exc:
        raise ValueError("world region difficulty must be an integer") from exc
    if difficulty < 0:
        raise ValueError("world region difficulty must not be negative")

    dangers = _string_sequence(record.get("dangers"), field_name="dangers")
    points = _point_records(record.get("points_of_interest"))

    consumed = {
        "id",
        "name",
        "difficulty",
        "bounds",
        "dangers",
        "points_of_interest",
    }
    metadata = {key: value for key, value in record.items() if key not in consumed}
    return WorldRegion(
        id=region_id,
        name=name,
        difficulty=difficulty,
        bounds=bounds,
        dangers=dangers,
        points_of_interest=points,
        metadata=metadata,
    )


def find_region_by_id(
    regions: Sequence[WorldRegion],
    region_id: str,
) -> WorldRegion | None:
    """Resolve one region by id and reject ambiguous duplicate catalogs."""

    normalized = region_id.strip()
    if not normalized:
        raise ValueError("region_id must not be empty")

    matches = [region for region in regions if region.id == normalized]
    if len(matches) > 1:
        raise ValueError(f"duplicate world region id: {normalized}")
    return matches[0] if matches else None


def find_region_at(
    regions: Sequence[WorldRegion],
    point: tuple[float, float],
) -> WorldRegion | None:
    """Resolve the unique region owning ``point`` using half-open bounds."""

    _validate_point(point, name="point")
    matches = [region for region in regions if region.bounds.contains(point)]
    if len(matches) > 1:
        ids = ", ".join(sorted(region.id for region in matches))
        raise ValueError(f"overlapping world regions at point {point}: {ids}")
    return matches[0] if matches else None


def calculate_supplies_needed(time_minutes: int) -> dict[str, int]:
    """Preserve the source voyage-supply policy as a pure function."""

    if time_minutes < 0:
        raise ValueError("time_minutes must not be negative")
    hours = time_minutes / 60
    return {
        "food": max(1, int(hours * 2)),
        "water": max(1, int(hours * 3)),
        "recommended_rum": max(0, int(hours - 2)),
        "recommended_oranges": max(0, int(hours / 2)),
    }


def _segment_intersects_bounds(
    start: tuple[float, float],
    end: tuple[float, float],
    bounds: WorldBounds,
) -> bool:
    """Return whether a line segment intersects an axis-aligned region.

    The source implementation only checked x overlap. The promoted boundary
    keeps its intent (collect dangers from traversed regions) but fixes the
    false-positive behavior by clipping in both dimensions.
    """

    x0, y0 = start
    x1, y1 = end
    dx = x1 - x0
    dy = y1 - y0
    t_min = 0.0
    t_max = 1.0

    for origin, delta, lower, upper in (
        (x0, dx, bounds.x, bounds.max_x),
        (y0, dy, bounds.y, bounds.max_y),
    ):
        if delta == 0:
            if origin < lower or origin > upper:
                return False
            continue
        first = (lower - origin) / delta
        second = (upper - origin) / delta
        near = min(first, second)
        far = max(first, second)
        t_min = max(t_min, near)
        t_max = min(t_max, far)
        if t_min > t_max:
            return False
    return True


def calculate_route(
    start: tuple[float, float],
    end: tuple[float, float],
    regions: Sequence[WorldRegion],
    *,
    units_per_minute: float = 100.0,
) -> dict[str, Any]:
    """Calculate source-compatible route distance, time, dangers and supplies."""

    _validate_point(start, name="start")
    _validate_point(end, name="end")
    if not math.isfinite(units_per_minute) or units_per_minute <= 0:
        raise ValueError("units_per_minute must be finite and positive")
    distance = math.dist(start, end)
    estimated_time = int(distance / units_per_minute)

    dangers: list[str] = []
    seen: set[str] = set()
    for region in regions:
        if not _segment_intersects_bounds(start, end, region.bounds):
            continue
        for danger in region.dangers:
            if danger not in seen:
                seen.add(danger)
                dangers.append(danger)

    return {
        "distance": round(distance, 2),
        "estimated_time_minutes": estimated_time,
        "dangers_on_route": dangers,
        "recommended_supplies": calculate_supplies_needed(estimated_time),
    }


def project_fog_of_war(
    regions: Sequence[WorldRegion],
    discovered_location_ids: Sequence[str],
) -> dict[str, Any]:
    """Project discovery state over source-shaped region points of interest."""

    discovered = {str(value) for value in discovered_location_ids}
    locations: list[dict[str, Any]] = []
    for region in regions:
        for poi in region.points_of_interest:
            location_id = str(poi.get("id") or "").strip()
            if not location_id:
                continue
            locations.append(
                {
                    "id": location_id,
                    "region": region.id,
                    "discovered": location_id in discovered,
                }
            )

    discovered_count = sum(1 for location in locations if location["discovered"])
    total_count = len(locations)
    percentage = round(discovered_count / total_count * 100, 1) if total_count else 0.0
    return {
        "locations": locations,
        "discovered_count": discovered_count,
        "total_count": total_count,
        "exploration_percentage": percentage,
    }


@dataclass(frozen=True, slots=True)
class IslandVocabulary:
    prefixes: tuple[str, ...] = (
        "Mystery",
        "Lost",
        "Hidden",
        "Ancient",
        "Wild",
        "Coral",
        "Golden",
        "Crystal",
    )
    suffixes: tuple[str, ...] = (
        "Isle",
        "Atoll",
        "Cay",
        "Reef",
        "Haven",
        "Sanctuary",
    )
    features: tuple[str, ...] = (
        "pristine beaches",
        "dense jungle",
        "rocky cliffs",
        "volcanic crater",
        "freshwater spring",
        "ancient ruins",
        "mysterious cave",
        "crystal caves",
    )
    fish_types: tuple[str, ...] = (
        "beach_dwellers",
        "reef_fish",
        "tropical_fish",
        "rare_specimens",
        "legendary_variants",
        "unique_species",
    )
    moods: tuple[str, ...] = ("mysterious", "beautiful", "rugged", "peaceful")
    sizes: tuple[str, ...] = ("tiny", "small", "medium", "large")

    def validate(self) -> None:
        for name, values in (
            ("prefixes", self.prefixes),
            ("suffixes", self.suffixes),
            ("features", self.features),
            ("fish_types", self.fish_types),
            ("moods", self.moods),
            ("sizes", self.sizes),
        ):
            if not values:
                raise ValueError(f"island vocabulary {name} must not be empty")


def generate_random_island(
    region: WorldRegion,
    user_id: str,
    *,
    rng: random.Random,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    id_factory: Callable[[], str] = lambda: str(uuid4()),
    vocabulary: IslandVocabulary = IslandVocabulary(),
) -> dict[str, Any]:
    """Generate a source-shaped island with all nondeterminism injected."""

    user_id = user_id.strip()
    if not user_id:
        raise ValueError("user_id must not be empty")
    if region.bounds.width <= 0 or region.bounds.height <= 0:
        raise ValueError("world region requires positive-area bounds for island generation")
    vocabulary.validate()

    island_id = str(id_factory()).strip()
    if not island_id:
        raise ValueError("id_factory must return a non-empty identifier")
    discovered_at = now()
    if discovered_at.tzinfo is None:
        raise ValueError("now must return a timezone-aware datetime")

    max_features = min(3, len(vocabulary.features))
    max_fish_types = min(3, len(vocabulary.fish_types))
    feature_count = rng.randint(1, max_features)
    fish_count = rng.randint(1, max_fish_types)
    features = rng.sample(vocabulary.features, feature_count)
    fish_types = rng.sample(vocabulary.fish_types, fish_count)
    name = f"{rng.choice(vocabulary.prefixes)} {rng.choice(vocabulary.suffixes)}"

    return {
        "id": island_id,
        "name": name,
        "region": region.id,
        "position": {
            "x": rng.randrange(region.bounds.x, region.bounds.max_x),
            "y": rng.randrange(region.bounds.y, region.bounds.max_y),
        },
        "size": rng.choice(vocabulary.sizes),
        "features": list(features),
        "description": (
            f"A {rng.choice(vocabulary.moods)} island with {', '.join(features)}."
        ),
        "fish_types": list(fish_types),
        "rare_fish_chance": 0.05 * region.difficulty,
        "discovered_by": user_id,
        "discovered_at": discovered_at.astimezone(timezone.utc).isoformat(),
        "has_beach_fishing": True,
        "has_secrets": rng.random() < 0.3,
        "danger_level": region.difficulty,
    }
