from datetime import datetime, timezone

import skeleton.frontier.gameplay as gameplay


def test_gameplay_facade_exposes_aquarium_surface_without_collisions():
    assert gameplay.AquariumState.__module__ == "skeleton.frontier.aquarium_state"
    assert gameplay.AquariumTankSpec.__module__ == "skeleton.frontier.aquarium_models"
    assert gameplay.DisplayFish.__module__ == "skeleton.frontier.aquarium_models"
    assert gameplay.quote_aquarium_purchase.__module__ == "skeleton.frontier.aquarium"
    assert gameplay.quote_equipment_purchase.__module__ == "skeleton.frontier.equipment"


def test_gameplay_facade_can_project_aquarium_transition_to_memory():
    starter = gameplay.AquariumTankSpec("starter", "Starter", 10, 1, 3)
    fish = gameplay.DisplayFish(
        "fish-1",
        "Blue Fish",
        "blue_fish",
        20,
        gameplay.AquariumPosition(50, 50),
    )
    state = gameplay.add_fish(gameplay.initial_aquarium(), starter, fish).aquarium
    event = gameplay.aquarium_event(
        state,
        subject_id="player-1",
        action="fish_added",
        occurred_at=datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc),
    )
    memory = gameplay.aquarium_event_to_memory_item(event)

    assert memory["metadata"]["fish_count"] == 1
    assert memory["metadata"]["aquarium_state_sha256"] == gameplay.aquarium_state_digest(state)
