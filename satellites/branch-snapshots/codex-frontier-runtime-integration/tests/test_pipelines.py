"""Tests for the Text-to-X pipelines."""

import pytest

from skeleton.kernel.errors import ValidationError
from skeleton.pipelines import (
    AnimationPipeline,
    GameLogicPipeline,
    NpcPipeline,
)


class TestNpcPipeline:
    def test_deterministic(self):
        p1, p2 = NpcPipeline(), NpcPipeline()
        s1 = p1.run("a grizzled dockworker who knows too much")
        s2 = p2.run("a grizzled dockworker who knows too much")
        assert s1.archetype == s2.archetype
        assert s1.persona == s2.persona

    def test_full_spec(self):
        spec = NpcPipeline().run("a cheerful blacksmith", dialogue_beats=3)
        assert spec.dialogue_tree[0].node_id == "root"
        assert spec.dialogue_tree[-1].node_id == "farewell"
        assert {s.name for s in spec.behaviour_graph} >= {"idle", "greet", "alert"}
        assert spec.persona["traits"]

    def test_events_emitted(self):
        from skeleton.kernel.events import EventBus
        bus = EventBus()
        topics = []
        bus.subscribe("pipeline.*", lambda e: topics.append(e.topic))
        NpcPipeline(bus=bus).run("a spy")
        assert "pipeline.npc.started" in topics
        assert "pipeline.npc.completed" in topics

    def test_empty_description_rejected(self):
        with pytest.raises(ValidationError):
            NpcPipeline().run("   ")

    def test_beats_bounds(self):
        with pytest.raises(ValidationError):
            NpcPipeline().run("x", dialogue_beats=99)

    def test_injected_generator(self):
        spec = NpcPipeline(generator=lambda d, p: {"archetype": "mentor", "traits": ["calm"]}).run("x")
        assert spec.archetype == "mentor"


class TestGameLogicPipeline:
    def test_invariants(self):
        spec = GameLogicPipeline().run("a space trading game")
        assert all(v > 0 for v in spec.combat.base_values.values())
        assert spec.economy.is_closed()
        assert spec.progression.xp_for_level(2) > spec.progression.xp_for_level(1)

    def test_damage_formula(self):
        spec = GameLogicPipeline().run("x")
        assert spec.combat.damage(10.0, 0.0) == 10.0
        assert spec.combat.damage(10.0, 100.0) == 5.0

    def test_bad_curve_rejected(self):
        with pytest.raises(ValidationError):
            GameLogicPipeline().run("x", curve="sideways")

    def test_level_bounds(self):
        spec = GameLogicPipeline().run("x", max_level=10)
        with pytest.raises(ValidationError):
            spec.progression.xp_for_level(11)


class TestAnimationPipeline:
    def test_structure(self):
        spec = AnimationPipeline().run("a knight")
        assert "root" in spec.rig
        assert len(spec.clips) == 4
        names = {c.name for c in spec.clips}
        assert names == {"idle", "walk", "run", "attack"}
        assert spec.blend_tree["type"] == "blend_1d"

    def test_custom_actions(self):
        spec = AnimationPipeline().run("a mage", actions=("idle", "cast"))
        assert {c.name for c in spec.clips} == {"idle", "cast"}

    def test_loops_only_locomotion(self):
        spec = AnimationPipeline().run("x")
        loops = {c.name: c.loop for c in spec.clips}
        assert loops["idle"] and loops["walk"] and loops["run"]
        assert not loops["attack"]

    def test_no_actions_rejected(self):
        with pytest.raises(ValidationError):
            AnimationPipeline().run("x", actions=())
