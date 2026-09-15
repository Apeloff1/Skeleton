from __future__ import annotations

import random
from datetime import datetime, timezone

import pytest

from skeleton.frontier.world import (
    calculate_route,
    calculate_supplies_needed,
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


def test_region_adapter_preserves_domain_metadata_without_catalog_copy():
    region = _region()

    assert region.id == "harbor"
    assert region.difficulty == 3
    assert region.bounds.max_x == 100
    assert region.metadata["theme"] == "coastal"
    assert region.points_of_interest[0]["id"] == "harbor-dock"


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
    assert 300 <= first["position"]["x"] <= 400
    assert 200 <= first["position"]["y"] <= 300
    assert 1 <= len(first["features"]) <= 3
    assert 1 <= len(first["fish_types"]) <= 3
