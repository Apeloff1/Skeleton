from core.creature_ai import Creature, CreatureState, CreatureTraits, Stimulus
from core.world_agents import AgentSchedule, NavigationError, NavigationGraph, ScheduleEntry, WorldAgent, WorldNode


def test_navigation_shortest_path_and_agent_progression():
    graph = NavigationGraph([
        WorldNode("home", 0, 0, connections=("square",)),
        WorldNode("square", 1, 0, connections=("home", "dock")),
        WorldNode("dock", 2, 0, connections=("square",)),
    ])
    schedule = AgentSchedule((ScheduleEntry(0, "sleep", "home"), ScheduleEntry(360, "work", "dock")))
    agent = WorldAgent("npc-1", "home", schedule)
    assert agent.plan_to(graph, "dock") == ("home", "square", "dock")
    assert agent.advance() == "square"
    assert agent.advance() == "dock"
    assert agent.advance() == "dock"


def test_navigation_rejects_unknown_edges_and_unreachable_routes():
    try:
        NavigationGraph([WorldNode("a", 0, 0, connections=("missing",))])
        assert False, "expected invalid connection to fail"
    except NavigationError:
        pass
    graph = NavigationGraph([WorldNode("a", 0, 0), WorldNode("b", 1, 0)])
    try:
        graph.shortest_path("a", "b")
        assert False, "expected unreachable route to fail"
    except NavigationError:
        pass


def test_schedule_context_override_and_wraparound():
    schedule = AgentSchedule(
        entries=(ScheduleEntry(300, "work", "market"), ScheduleEntry(1200, "sleep", "home")),
        overrides={"storm": (ScheduleEntry(300, "shelter", "home"),)},
    )
    assert schedule.activity_at(420).action == "work"
    assert schedule.activity_at(420, contexts=("storm",)).action == "shelter"
    assert schedule.activity_at(60).action == "sleep"


def test_sync_schedule_plans_toward_activity_location():
    graph = NavigationGraph([
        WorldNode("home", 0, 0, connections=("market",)),
        WorldNode("market", 1, 0, connections=("home",)),
    ])
    schedule = AgentSchedule((ScheduleEntry(0, "sleep", "home"), ScheduleEntry(480, "work", "market")))
    agent = WorldAgent("merchant", "home", schedule)
    activity = agent.sync_schedule(graph, 600)
    assert activity.location == "market"
    assert agent.path == ("home", "market")


def test_creature_prioritizes_survival_over_food():
    creature = Creature(traits=CreatureTraits(caution=0.8, curiosity=0.9))
    state = creature.update(
        1.0,
        [Stimulus("food", 2, 0), Stimulus("predator", 1, 0, intensity=1.0)],
        seed=1,
    )
    assert state == CreatureState.FLEEING
    assert creature.vx < 0


def test_hungry_creature_seeks_food_and_moves_toward_it():
    creature = Creature(hunger=90, x=0, y=0)
    state = creature.update(1.0, [Stimulus("bait", 10, 0)], seed=1)
    assert state == CreatureState.SEEKING
    assert creature.x > 0


def test_tired_creature_rests_and_recovers():
    creature = Creature(energy=10, vx=2, vy=0)
    before = creature.energy
    state = creature.update(1.0, [], seed=1)
    assert state == CreatureState.RESTING
    assert creature.energy > before
    assert abs(creature.vx) < 2


def test_creature_ai_is_seed_deterministic_for_idle_wander():
    a = Creature()
    b = Creature()
    a.update(10.0, [], seed=9)
    b.update(10.0, [], seed=9)
    assert (a.x, a.y, a.vx, a.vy) == (b.x, b.y, b.vx, b.vy)
