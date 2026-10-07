import pytest

from core.achievement_engine import AchievementEngine, AchievementRule
from core.discovery_engine import DiscoveryEngine, DiscoveryRule
from core.relationship_memory import RelationshipMemory
from core.travel_graph import Location, Region, TravelGraph


def test_relationship_memory_bounds_history_and_modifiers():
    memory = RelationshipMemory("npc", max_history=2)
    memory.record("compliment", topic="sea")
    memory.record("saved_life", trust_delta=15)
    memory.record("gift_loved")
    assert len(memory.history) == 2
    assert memory.relationship == 83
    assert memory.trust == 15
    assert memory.tier() == "best_friend"
    assert memory.modifiers().price_multiplier == 0.70
    assert memory.remembers_topic("sea") is False


def test_relationship_quest_events_are_idempotent():
    memory = RelationshipMemory("npc")
    memory.mark_quest("q1", completed=True)
    memory.mark_quest("q1", completed=True)
    assert memory.relationship == 20
    assert memory.trust == 5


def test_travel_graph_prefers_safer_route_when_weighted():
    graph = TravelGraph(
        [Region("coast")],
        [
            Location("a", "coast", 0, 0),
            Location("b", "coast", 1, 0),
            Location("c", "coast", 2, 0),
        ],
    )
    graph.connect("a", "c", distance=1, danger=10)
    graph.connect("a", "b", distance=2, danger=0)
    graph.connect("b", "c", distance=2, danger=0)
    plan = graph.plan("a", "c", level=1, danger_weight=1)
    assert plan.locations == ("a", "b", "c")
    assert plan.distance == 4


def test_travel_graph_enforces_level_discovery_and_route_tags():
    graph = TravelGraph(
        [Region("coast")],
        [Location("a", "coast", 0, 0), Location("b", "coast", 1, 0, min_level=3)],
    )
    graph.connect("a", "b", required_tags=("boat",))
    with pytest.raises(ValueError):
        graph.plan("a", "b", level=2, tags=("boat",))
    with pytest.raises(ValueError):
        graph.plan("a", "b", level=3)
    graph.discover("a")
    graph.discover("b")
    assert graph.plan("a", "b", level=3, tags=("boat",), discovered_only=True).locations == ("a", "b")


def test_discovery_engine_nested_facts_and_exactly_once_unlocks():
    engine = DiscoveryEngine(
        [
            DiscoveryRule("legendary", "catch.legendary", "gte", 5, ("legendary_feast",)),
            DiscoveryRule("seasons", "seasons", "contains_all", ["spring", "winter"], ("seasonal",)),
        ]
    )
    first = engine.evaluate({"catch": {"legendary": 5}, "seasons": ["spring", "winter"]})
    assert first.newly_discovered == ("legendary", "seasons")
    assert set(first.newly_unlocked) == {"legendary_feast", "seasonal"}
    second = engine.evaluate({"catch": {"legendary": 10}, "seasons": ["spring", "winter"]})
    assert second.newly_discovered == ()


def test_discovery_engine_rejects_duplicate_generator_rules():
    rules = (
        rule
        for rule in [
            DiscoveryRule("x", "a", "eq", 1, ("one",)),
            DiscoveryRule("x", "b", "eq", 2, ("two",)),
        ]
    )
    with pytest.raises(ValueError):
        DiscoveryEngine(rules)


def test_achievement_engine_is_monotonic_and_unlocks_once():
    engine = AchievementEngine(
        [
            AchievementRule("catch10", "catches", 10, {"xp": 50}),
            AchievementRule("catch20", "catches", 20),
        ]
    )
    assert engine.increment("catches", 8) == ()
    unlocks = engine.increment("catches", 2)
    assert [event.id for event in unlocks] == ["catch10"]
    engine.set_metric("catches", 1)
    assert engine.metrics["catches"] == 10
    assert engine.increment("catches", 10)[0].id == "catch20"
    assert engine.increment("catches", 1) == ()
