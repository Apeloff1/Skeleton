from __future__ import annotations

import math
import random
from datetime import datetime, timezone

import pytest

from skeleton.frontier.world import (
    calculate_route,
    calculate_supplies_needed,
    find_region_at,
    find_region_by_id,
    generate_random_island,
    project_fog_of_war,
    region_from_record,
)


def _region(*, region_id="harbor", x=0, y=0, dangers=None):
    return region_from_record(
        {
            "id": region_id,
            "name": region_id.title(),
            "difficulty": 3,
            "theme": "coastal",
            "bounds": {"x": x, "y": y, "width": 100, "height": 100},
            "dangers": dangers or [],
            "points_of_interest": [
                {"id": f"{region_id}-dock", "name": "Dock", "type": "port"},
                {"id": f"{region_id}-reef", "name": "Reef", "type": "fishing"},
            ],
        }
    )


def _record(**overrides):
    record = {
        "id": "harbor",
        "name": "Harbor",
        "difficulty": 3,
        "bounds": {"x": 0, "y": 0, "width": 100, "height": 100},
        "dangers": ["storm"],
        "points_of_interest": [{"id": "dock", "name": "Dock"}],
    }
    record.update(overrides)
    return record


def test_region_adapter_preserves_domain_metadata_without_catalog_copy():
    region = _region()

    assert region.id == "harbor"
    assert region.difficulty == 3
    assert region.bounds.max_x == 100
    assert region.metadata["theme"] == "coastal"
    assert region.points_of_interest[0]["id"] == "harbor-dock"


def test_region_adapter_rejects_string_dangers_instead_of_splitting_characters():
    with pytest.raises(TypeError, match="dangers must be a sequence"):
        region_from_record(_record(dangers="storm"))


def test_region_adapter_rejects_malformed_point_records_instead_of_dropping_them():
    with pytest.raises(TypeError, match=r"points_of_interest\[1\] must be a mapping"):
        region_from_record(
            _record(points_of_interest=[{"id": "dock"}, "not-a-point"])
        )


def test_region_lookup_uses_half_open_edges_for_adjacent_regions():
    west = _region(region_id="west", x=0)
    east = _region(region_id="east", x=100)
    regions = [west, east]

    assert find_region_at(regions, (0, 50)) is west
    assert find_region_at(regions, (99.999, 50)) is west
    assert find_region_at(regions, (100, 50)) is east
    assert find_region_at(regions, (200, 50)) is None
    assert find_region_by_id(regions, "east") is east
    assert find_region_by_id(regions, "missing") is None


def test_region_lookup_fails_closed_for_ambiguous_catalogs():
    duplicate_a = _region(region_id="duplicate", x=0)
    duplicate_b = _region(region_id="duplicate", x=200)
    with pytest.raises(ValueError, match="duplicate world region id"):
        find_region_by_id([duplicate_a, duplicate_b], "duplicate")

    overlap_a = _region(region_id="overlap-a", x=0)
    overlap_b = _region(region_id="overlap-b", x=50)
    with pytest.raises(ValueError, match="overlapping world regions"):
        find_region_at([overlap_a, overlap_b], (75, 50))


def test_region_lookup_rejects_non_finite_coordinates():
    with pytest.raises(ValueError, match="finite numeric coordinates"):
        find_region_at([_region()], (math.inf, 50))


def test_route_policy_uses_two_dimensional_region_intersection():
    traversed = _region(region_id="traversed", dangers=["storm", "reef"])
    same_x_wrong_y = _region(
        region_id="wrong-y",
        x=0,
        y=500,
        dangers=["phantom"],
    )

    route = calculate_route((0, 50), (100, 50), [traversed, same_x_wrong_y])

    assert route["distance"] == 100.0
    assert route["estimated_time_minutes"] == 1
    assert route["dangers_on_route"] == ["storm", "reef"]
    assert "phantom" not in route["dangers_on_route"]
    assert route["recommended_supplies"] == {
        "food": 1,
        "water": 1,
        "recommended_rum": 0,
        "recommended_oranges": 0,
    }


def test_route_policy_rejects_non_finite_inputs():
    region = _region()
    with pytest.raises(ValueError, match="start must contain finite numeric coordinates"):
        calculate_route((math.nan, 0), (1, 1), [region])
    with pytest.raises(ValueError, match="units_per_minute must be finite and positive"):
        calculate_route((0, 0), (1, 1), [region], units_per_minute=math.inf)


def test_supply_policy_rejects_negative_time_and_preserves_source_formula():
    assert calculate_supplies_needed(180) == {
        "food": 6,
        "water": 9,
        "recommended_rum": 1,
        "recommended_oranges": 1,
    }
    with pytest.raises(ValueError, match="must not be negative"):
        calculate_supplies_needed(-1)


def test_fog_projection_is_pure_and_counts_known_points():
    first = _region(region_id="first")
    second = _region(region_id="second", x=100)

    fog = project_fog_of_war(
        [first, second],
        ["first-dock", "second-reef", "not-in-catalog"],
    )

    assert fog["total_count"] == 4
    assert fog["discovered_count"] == 2
    assert fog["exploration_percentage"] == 50.0
    assert [
        location["id"]
        for location in fog["locations"]
        if location["discovered"]
    ] == ["first-dock", "second-reef"]


def test_random_island_generation_injects_rng_clock_and_identity():
    region = _region(region_id="storm-straits", x=300, y=200)
    fixed_time = datetime(2026, 9, 15, 9, 45, tzinfo=timezone.utc)

    first = generate_random_island(
        region,
        "user-7",
        rng=random.Random(7),
        now=lambda: fixed_time,
        id_factory=lambda: "island-7",
    )
    second = generate_random_island(
        region,
        "user-7",
        rng=random.Random(7),
        now=lambda: fixed_time,
        id_factory=lambda: "island-7",
    )

    assert first == second
    assert first["id"] == "island-7"
    assert first["region"] == "storm-straits"
    assert first["discovered_by"] == "user-7"
    assert first["discovered_at"] == "2026-09-15T09:45:00+00:00"
    assert first["rare_fish_chance"] == pytest.approx(0.15)
    assert 300 <= first["position"]["x"] < 400
    assert 200 <= first["position"]["y"] < 300
    assert region.bounds.contains((first["position"]["x"], first["position"]["y"]))
    assert 1 <= len(first["features"]) <= 3
    assert 1 <= len(first["fish_types"]) <= 3


def test_random_island_generation_rejects_ambiguous_clock_and_identity():
    region = _region()
    with pytest.raises(ValueError, match="id_factory must return a non-empty identifier"):
        generate_random_island(
            region,
            "user-7",
            rng=random.Random(7),
            id_factory=lambda: " ",
        )

    with pytest.raises(ValueError, match="timezone-aware"):
        generate_random_island(
            region,
            "user-7",
            rng=random.Random(7),
            id_factory=lambda: "island-7",
            now=lambda: datetime(2026, 9, 15, 9, 45),
        )


def test_random_island_generation_rejects_zero_area_regions():
    zero_width = region_from_record(
        _record(bounds={"x": 0, "y": 0, "width": 0, "height": 100})
    )
    with pytest.raises(ValueError, match="positive-area bounds"):
        generate_random_island(
            zero_width,
            "user-7",
            rng=random.Random(7),
            id_factory=lambda: "island-7",
        )
