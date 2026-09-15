from datetime import datetime, timezone

import skeleton.frontier.gameplay as gameplay

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def test_gameplay_facade_uses_single_canonical_aquarium_module():
    assert gameplay.AquariumState.__module__ == "skeleton.frontier.aquarium"
    assert gameplay.AquariumTankSpec.__module__ == "skeleton.frontier.aquarium"
    assert gameplay.AquariumThemeSpec.__module__ == "skeleton.frontier.aquarium"
    assert gameplay.DisplayFish.__module__ == "skeleton.frontier.aquarium"
    assert gameplay.aquarium_event.__module__ == "skeleton.frontier.aquarium_adapters"
    assert gameplay.quote_equipment_purchase.__module__ == "skeleton.frontier.equipment"


def test_gameplay_facade_projects_canonical_aquarium_state_to_memory():
    tank = gameplay.AquariumTankSpec("starter", "Starter", 10, 100, 50, 3)
    fish = gameplay.DisplayFish(
        "fish-1",
        "Blue Fish",
        "blue_fish",
        20,
        "#4A90D9",
        {},
        gameplay.AquariumPosition(50, 50),
        NOW,
    )
    state = gameplay.add_fish(gameplay.initial_aquarium(), tank, fish).aquarium
    event = gameplay.aquarium_event(
        state,
        subject_id="player-1",
        action="fish_added",
        occurred_at=NOW,
    )
    memory = gameplay.aquarium_event_to_memory_item(event)

    assert memory["metadata"]["fish_count"] == 1
    assert memory["metadata"]["aquarium_state_sha256"] == gameplay.aquarium_state_digest(state)
