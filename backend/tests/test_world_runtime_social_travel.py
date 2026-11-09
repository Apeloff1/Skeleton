from core.achievement_engine import AchievementEngine, AchievementRule
from core.discovery_engine import DiscoveryEngine, DiscoveryRule
from core.travel_graph import Location, Region, TravelGraph
from core.world_agents import AgentSchedule, NavigationGraph, ScheduleEntry, WorldAgent, WorldNode
from core.world_runtime import WorldRuntime


def make_runtime():
    nav = NavigationGraph(
        [
            WorldNode("dock", 0, 0, connections=("market",)),
            WorldNode("market", 1, 0, connections=("dock",)),
        ]
    )
    agent = WorldAgent(
        "merchant",
        "dock",
        AgentSchedule((ScheduleEntry(0, "work", "market"),)),
    )
    travel = TravelGraph(
        [Region("coast")],
        [Location("dock", "coast", 0, 0), Location("island", "coast", 10, 0)],
    )
    travel.connect("dock", "island", danger=2, required_tags=("boat",))
    discoveries = DiscoveryEngine(
        [DiscoveryRule("starter", "player.level", "gte", 1, ("starter_recipe",))]
    )
    achievements = AchievementEngine(
        [AchievementRule("traveler", "locations_discovered", 2, {"xp": 100})]
    )
    return WorldRuntime(
        graph=nav,
        agents=[agent],
        travel_graph=travel,
        discovery_engine=discoveries,
        achievement_engine=achievements,
    )


def test_world_runtime_relationships_are_agent_scoped():
    runtime = make_runtime()
    memory = runtime.relationship("merchant")
    memory.record("compliment")
    assert runtime.snapshot()["relationships"]["merchant"]["relationship"] == 8


def test_world_runtime_travel_discovery_and_achievements_compose():
    runtime = make_runtime()
    assert runtime.discover_location("dock") is True
    assert runtime.discover_location("island") is True
    plan = runtime.plan_travel("dock", "island", tags=("boat",), discovered_only=True)
    assert plan.locations == ("dock", "island")
    unlock = runtime.record_metric("locations_discovered", 2)
    assert unlock[0].id == "traveler"
    discovery = runtime.evaluate_discoveries()
    assert discovery.newly_unlocked == ("starter_recipe",)
    snapshot = runtime.snapshot()
    assert snapshot["travel"]["discovered"] == ["dock", "island"]
    assert snapshot["achievements"]["unlocked"] == ["traveler"]
    assert snapshot["discoveries"]["unlocked"] == ["starter_recipe"]


def test_world_runtime_save_includes_extended_systems():
    runtime = make_runtime()
    runtime.relationship("merchant").record("saved_life")
    runtime.discover_location("dock")
    runtime.evaluate_discoveries()
    encoded = runtime.encode_save()
    assert '"relationships"' in encoded
    assert '"discoveries"' in encoded
    assert '"travel"' in encoded
