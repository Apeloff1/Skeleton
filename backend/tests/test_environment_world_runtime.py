import pytest

from core.character_profile import CharacterProfile
from core.creature_ai import Creature, Stimulus
from core.environment_runtime import EnvironmentRuntime
from core.save_envelope import SaveIntegrityError
from core.skill_graph import SkillDefinition, SkillGraph
from core.world_agents import AgentSchedule, NavigationGraph, ScheduleEntry, WorldAgent, WorldNode
from core.world_runtime import WorldRuntime


def test_weather_transition_is_bounded_and_deterministic():
    a = EnvironmentRuntime(weather="sunny")
    b = EnvironmentRuntime(weather="sunny")
    a.set_weather("storm")
    b.set_weather("storm")
    state_a = a.step(10, transition_seconds=20, seed=7)
    state_b = b.step(10, transition_seconds=20, seed=7)
    assert state_a == state_b
    assert 0 < a.progress < 1
    assert 0 <= state_a.visibility <= 1
    assert state_a.wind_speed >= 0


def test_weather_contexts_surface_gameplay_conditions():
    env = EnvironmentRuntime(weather="sunny")
    env.set_weather("storm", instant=True)
    assert {"storm", "rainy", "stormy"}.issubset(set(env.contexts()))


def build_runtime() -> WorldRuntime:
    graph = NavigationGraph([
        WorldNode("home", 0, 0, connections=("market",)),
        WorldNode("market", 1, 0, connections=("home",)),
    ])
    schedule = AgentSchedule((
        ScheduleEntry(0, "sleep", "home"),
        ScheduleEntry(1, "work", "market"),
    ))
    skills = SkillGraph([
        SkillDefinition("navigation", "exploration", 1, (5,), {"route_speed": 0.1}),
    ])
    runtime = WorldRuntime(
        graph=graph,
        agents=[WorldAgent("merchant", "home", schedule)],
        creatures={"fish": Creature(hunger=90)},
        character=CharacterProfile("Mara", level=2),
        skill_graph=skills,
    )
    runtime.skill_profile.points = 10
    return runtime


def test_world_tick_composes_agents_creatures_environment_and_time():
    runtime = build_runtime()
    tick = runtime.tick(
        minutes=1,
        dt=1,
        stimuli={"fish": [Stimulus("food", 5, 0)]},
        seed=4,
    )
    assert tick.minute == 1
    assert tick.agent_locations["merchant"] == "market"
    assert tick.creature_states["fish"] == "seeking"
    assert tick.weather == "sunny"


def test_world_runtime_skill_purchase_uses_character_level_and_points():
    runtime = build_runtime()
    assert runtime.purchase_skill("navigation") == 1
    assert runtime.skill_profile.points == 5


def test_world_snapshot_encodes_with_integrity_envelope():
    runtime = build_runtime()
    raw = runtime.encode_save()
    decoded = runtime.save_codec.decode(raw)
    assert decoded.payload["character"]["name"] == "Mara"
    assert decoded.payload["agents"]["merchant"] == "home"


def test_world_save_tampering_fails_closed():
    runtime = build_runtime()
    raw = runtime.encode_save().replace('"Mara"', '"Mallory"')
    with pytest.raises(SaveIntegrityError):
        runtime.save_codec.decode(raw)


def test_world_runtime_rejects_duplicate_agents():
    graph = NavigationGraph([WorldNode("home", 0, 0)])
    schedule = AgentSchedule((ScheduleEntry(0, "sleep", "home"),))
    with pytest.raises(ValueError, match="duplicate"):
        WorldRuntime(
            graph=graph,
            agents=[WorldAgent("same", "home", schedule), WorldAgent("same", "home", schedule)],
        )
