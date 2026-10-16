"""Focused, adversarial dynamic-world/game-authoring regression suite.

Execute explicitly:
    python -m unittest tests.test_jeeves_director_dynamic_world
No new compulsory workflow, noisy CI notification, or broad test gate.
"""
from __future__ import annotations

import http.client
from http.server import HTTPServer
import json
from dataclasses import replace
from pathlib import Path
import tempfile
import threading
import unittest

from skeleton.ai.game_builder.quest_scene_forge import (
    forge_director, compile_director_blueprint,
)
from skeleton.ai.game_builder.quest_scene_engine import (
    DirectorAction, available_director_actions,
    director_initial, director_step,
)
from skeleton.ai.game_builder.quest_world_dynamics import (
    Faction, Gate, Passage, Requirements, Influence, WorldDynamics,
    StandingRequirement, compile_dynamics,
)
from skeleton.developer.game_cli import SCHEMA as GAME_SCHEMA, run_game_cli
from skeleton.developer.jeeves_game_director_session import (
    begin, choose, inspect, _load,
)
from skeleton.developer.jeeves_game_director_labyrinth import plan
from skeleton.developer.jeeves_game_director_dynamic_audit import audit, analyze
from skeleton.developer.jeeves_game_director_dynamic_author import (
    preview, publish,
)
from skeleton.developer.jeeves_game_dragon_world import study, queue, compare
from skeleton.developer.jeeves_game_director_bridge import handler
from skeleton.developer.jeeves_game_director_events import delta
from skeleton.developer.jeeves_game_director_causality import (
    audit as causal_audit, contrast as causal_contrast,
)
from skeleton.developer.jeeves_game_dragon_navigation import study as navigation_study
from skeleton.developer.jeeves_game_dragon_policy import _context

from skeleton.developer.jeeves_game_director_atlas import export, verify


class OriginalLivingWorldTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "original_game"
        self.root.mkdir()
        (self.root / "design").mkdir()
        (self.root / "skeleton.game.json").write_text(json.dumps({
            "schema": GAME_SCHEMA, "name": "original_game",
            "vision": "An original frontier built around moral choices",
            "era": "extraction_now", "archetype": "auto",
        }))
        self.base = forge_director(
            "original_game", seed=41,
            regions=("harbor", "mountain", "ruins", "garden", "tower"),
            quest_types=("main_story", "investigation"), stages=2,
        )
        self.legacy_file = "design/director_campaign_source.json"
        (self.root / self.legacy_file).write_text(json.dumps({
            "schema": "skeleton.jeeves.director_campaign_source.v1",
            "director_world": self.base.payload(),
            "author_review_acknowledged": True,
        }))
        self.start = self.base.starting_scene
        self.neighbor = next(s for s in self.base.scenes if s.key in
                             next(x for x in self.base.scenes
                                  if x.key == self.start).links).key
        self.status = self.make_status_world()
        self.dynamic_file = "design/director_campaign_dynamic_source.json"
        (self.root / self.dynamic_file).write_text(json.dumps({
            "schema": "skeleton.jeeves.director_campaign_source.v1",
            "director_world": self.status.payload(),
            "author_review_acknowledged": True,
        }))

    def make_status_world(self):
        q = next(q for q in self.base.quests if q.scope == "main")
        choice = q.stages[0].solutions[0].outcome_flag
        # This producer is present in the original authored world, whether
        # or not a particular player has personally acquired it yet.
        candidates = [(s, a) for s in self.base.scenes for a in s.affordances
                      if a.produces is not None]
        ticket = candidates[0][1].produces if candidates else None
        requirements = Requirements(
            world_flags=("charter",),
            standings=(StandingRequirement("council", 25, 1000),),
        )
        events = (
            Passage(
                key="ferry", source=self.start, destination=self.neighbor,
                mode="ferry", name="The original harbor ferry",
                cost_turns=4, bidirectional=True,
                requirements=Requirements(),
                grant_world_flag="charter",
                reputation_change=(("council", 30),),
            ),
            Passage(
                key="express", source=self.start, destination=self.neighbor,
                mode="rail", name="Original guild rail",
                cost_turns=1, bidirectional=True,
                requirements=requirements,
            ),
        )
        if ticket is not None:
            events += (Passage(
                key="ticketed", source=self.start, destination=self.neighbor,
                mode="airship", name="One-way original express",
                cost_turns=1, requirements=Requirements(items=(ticket,)),
                consume_item=ticket,
            ),)
        dynamics = WorldDynamics(
            factions=(Faction("council", "The Original Council", 0),),
            gates=(Gate(self.start, self.neighbor, requirements,
                        "The guarded harbor gate"),),
            passages=events,
            influences=(Influence(
                key="story_charter", trigger="quest_result",
                faction="council", delta=10, quest=q.key,
                outcome_flag=choice, grant_world_flag="charter",
            ),),
        )
        doc = self.base.payload()
        doc["dynamics"] = dynamics.payload()
        return compile_director_blueprint(doc, human_reviewed=True)

    def _start(self, name="hero", source=None):
        return begin(self.root, source=source or self.dynamic_file, session=name)

    def _step(self, name, value):
        before = inspect(self.root, session=name)
        return choose(
            self.root, session=name, choice=value,
            expected_sequence=before["sequence"],
            expected_state_sha256=before["current_state_sha256"],
        )

    def test_old_world_and_journal_contract_remain_unchanged(self):
        old = compile_director_blueprint(self.base.payload(), human_reviewed=True)
        self.assertEqual(old.digest, self.base.digest)
        self.assertEqual(old.payload(), self.base.payload())
        self.assertNotIn("dynamics", old.payload())
        state = director_initial(old)
        self.assertNotIn("world_state", state.payload())
        self.assertNotIn("world_state", state.payload())
        original = self._start("legacy", self.legacy_file)
        self.assertNotIn("transport_options", original)
        self.assertTrue(any(a["kind"] == "travel" and a["key"] == self.neighbor
                            for a in original["actions"]))
        self._step("legacy", "wait:wait")
        self.assertEqual(inspect(self.root, session="legacy")["sequence"], 1)

    def test_conditional_walking_gate_and_real_ferry_reputation(self):
        beginning = self._start()
        self.assertEqual(beginning["world_state"]["standings"], [["council", 0]])
        self.assertEqual(beginning["world_state"]["world_flags"], [])
        self.assertFalse(any(
            x["kind"] == "travel" and x["key"] == self.neighbor
            for x in beginning["actions"]
        ))
        self.assertTrue(any(x["choice"] == "transit:ferry"
                            for x in beginning["actions"]))
        self.assertFalse(any(x["choice"] == "transit:express"
                             for x in beginning["actions"]))
        self.assertEqual(len(beginning["conditional_walking_links_blocked"]), 1)
        reached = self._step("hero", "transit:ferry")
        self.assertEqual(reached["scene"], self.neighbor)
        self.assertEqual(reached["turn"], 4)
        self.assertEqual(reached["world_state"]["standings"], [["council", 30]])
        self.assertEqual(reached["world_state"]["world_flags"], ["charter"])
        self.assertEqual(reached["world_state"]["passage_uses"], [["ferry", 1]])
        returned = self._step("hero", "transit:ferry")
        self.assertEqual(returned["scene"], self.start)
        self.assertEqual(returned["world_state"]["standings"], [["council", 60]])
        self.assertEqual(returned["sequence"], 2)
        self.assertTrue(any(
            x["choice"] == "travel:" + self.neighbor for x in returned["actions"]
        ))
        self.assertTrue(any(
            x["choice"] == "transit:express" for x in returned["actions"]
        ))
        status = inspect(self.root, session="hero")
        self.assertEqual(status["current_state_sha256"],
                         returned["current_state_sha256"])
        moved = self._step("hero", "travel:" + self.neighbor)
        self.assertEqual(moved["turn"], 9)
        self.assertEqual(moved["world_state"]["passage_uses"], [["ferry", 2]])
        self.assertEqual(_load(self.root, name="hero")[5], 3)
        with self.assertRaises(ValueError):
            self._step("hero", "transit:unknown")

    def test_every_transport_is_authoritative_and_cannot_be_forged(self):
        self._start()
        state = director_initial(self.status)
        illegal = DirectorAction("travel", self.neighbor, self.start)
        self.assertNotIn(illegal, available_director_actions(self.status, state))
        with self.assertRaises(ValueError):
            director_step(self.status, state, illegal)
        with self.assertRaises(ValueError):
            director_step(self.status, state,
                          DirectorAction("transit", "express", self.start))
        with self.assertRaises(ValueError):
            director_step(self.status, state,
                          DirectorAction("transit", "not_created", self.start))
        with self.assertRaises(ValueError):
            self._step("hero", "travel:" + self.neighbor)
        current = inspect(self.root, session="hero")
        self.assertEqual(current["sequence"], 0)

    def test_state_space_route_planning_can_unlock_and_use_transit(self):
        self._start()
        first = plan(self.root, session="hero", destination=self.neighbor,
                     profile="fastest", alternatives=3)
        self.assertTrue(first["faction_and_resource_states_simulated"])
        self.assertGreaterEqual(first["route_count"], 1)
        self.assertTrue(any(
            x["actions"][0] == "transit:ferry" for x in first["routes"]
        ))
        self.assertEqual(first["routes"][0]["steps"][0]["turns"], 4)
        self.assertEqual(first["routes"][0]["destination"], self.neighbor)
        self.assertEqual(inspect(self.root, session="hero")["sequence"], 0)
        self._step("hero", "transit:ferry")
        self._step("hero", "transit:ferry")
        second = plan(self.root, session="hero", destination=self.neighbor,
                      profile="fastest", alternatives=3)
        self.assertTrue(any(
            x["actions"][0] == "travel:" + self.neighbor
            or x["actions"][0] == "transit:express"
            for x in second["routes"]
        ))
        self.assertNotEqual(first["session_head_sha256"],
                            second["session_head_sha256"])
        self.assertTrue(all(x["canonical_actions_replayed"]
                            for x in second["routes"]))
        with self.assertRaises(ValueError):
            plan(self.root, session="hero", destination="../../other_game")

    def test_fare_is_consumed_only_when_it_was_actually_held(self):
        paid = next((p for p in self.status.dynamics.passages
                     if p.key == "ticketed"), None)
        if paid is None:
            self.skipTest("This particular original forge has no ticket-producing affordance")
        initial = director_initial(self.status)
        denied = DirectorAction("transit", paid.key, self.start)
        self.assertNotIn(denied, available_director_actions(self.status, initial))
        # Seed an explicit acquired-item precondition to isolate the engine's
        # resource-consumption logic; NOT an evidence claim about how the user
        # originally earned the item.
        equipped = replace(initial, acquired=(paid.consume_item,))
        self.assertIn(denied, available_director_actions(self.status, equipped))
        arrived = director_step(self.status, equipped, denied)
        self.assertEqual(arrived.scene, self.neighbor)
        self.assertNotIn(paid.consume_item, arrived.acquired)
        self.assertEqual(arrived.world_state.passage_uses, (("ticketed", 1),))
        with self.assertRaises(ValueError):
            director_step(self.status, arrived, denied)

    def test_dragon_policy_cannot_confuse_locked_and_unlocked_same_scene(self):
        start = director_initial(self.status)
        ferried = director_step(self.status, start,
                                DirectorAction("transit", "ferry", self.start))
        back = director_step(self.status, ferried,
                             DirectorAction("transit", "ferry", self.neighbor))
        self.assertEqual(start.scene, back.scene)
        self.assertEqual(start.stage_index, back.stage_index)
        self.assertNotEqual(_context(start), _context(back))
        self.assertEqual(back.world_state.standings, (("council", 60),))
        self.assertIn("charter", back.world_state.world_flags)

    def test_story_audit_and_navigation_distinguish_transport_from_footpath(self):
        self._start()
        self._step("hero", "transit:ferry")
        self._step("hero", "transit:ferry")
        ledger = causal_audit(self.root, session="hero", page_size=5)
        self.assertEqual(ledger["summary"]["transport_modes"]["ferry"], 2)
        self.assertEqual(ledger["summary"]["world_flags_created_at"]["charter"], 1)
        self.assertEqual(ledger["summary"]["faction_standing_changes"]["council"], 2)
        self.assertTrue(ledger["summary"]["world_consequence_edges"])
        maze = navigation_study(self.root, session="hero")
        self.assertEqual(maze["transport_uses"]["ferry"], 2)
        self.assertEqual(maze["travel_hops"], 0)
        self.assertEqual(maze["transport_turns"], 8)
        self.assertFalse(maze["walking_vs_multimodal_savings_conflated"])
        begin(self.root, source=self.dynamic_file, session="other")
        compared = causal_contrast(self.root, first="hero", second="other")
        self.assertTrue(compared["canon_story_differences_observed"])
        self.assertEqual(compared["world_flags_unique_to_first"], ["charter"])
        self.assertTrue(compared["faction_standing_differences"])

    def test_explicit_dynamics_consistency_assurance(self):
        self._start()
        report = audit(self.root, source=self.dynamic_file)
        doc = report["analysis"]
        self.assertEqual(doc["faction_count"], 1)
        self.assertEqual(doc["walking_gate_count"], 1)
        self.assertEqual(doc["initial_standings"], {"council": 0})
        self.assertFalse(doc["walking_gates"][0]["initially_open"])
        self.assertTrue(any(x["key"] == "ferry" and x["initially_open"]
                            for x in doc["transit_passages"]))
        self.assertFalse(doc["complete_dynamic_state_space_exhaustively_proven"])
        self.assertFalse(report["signoff_produced"])

    def test_schema_rejects_unsupported_faction_transport_and_unsafe_authoring(self):
        with self.assertRaises(ValueError):
            Passage(key="bad", source=self.start, destination=self.neighbor,
                    mode="made_up", name="A vehicle")
        with self.assertRaises(ValueError):
            Gate(source=self.start, destination=self.start)
        with self.assertRaises(ValueError):
            Passage(key="bad", source=self.start, destination=self.neighbor,
                    consume_item="ticket_not_required")
        with self.assertRaises(ValueError):
            Requirements(flags=("hope",), forbidden_flags=("hope",))
        with self.assertRaises(ValueError):
            WorldDynamics(
                factions=(Faction("guild", "Guild"),),
                passages=(Passage(
                    "unknown", self.start, self.neighbor,
                    reputation_change=(("other_faction", 200),)),),
            )
        authored = self.status.payload()
        authored["dynamics"]["unexpected_script"] = "__import__('os').system('x')"
        with self.assertRaises(ValueError):
            compile_director_blueprint(authored, human_reviewed=True)
        authored = self.status.payload()
        authored["dynamics"]["gates"][0]["requirements"]["items"] = [
            "key_not_produced",
        ]
        with self.assertRaises(ValueError):
            compile_director_blueprint(authored, human_reviewed=True)

    def test_labyrinth_blueprint_generation_requires_review_and_is_create_only(self):
        drafted = preview(self.root, source=self.legacy_file, intensity=4)
        self.assertTrue(drafted["ok"])
        self.assertFalse(drafted["published"])
        self.assertEqual(drafted["writes"], 0)
        self.assertGreaterEqual(
            drafted["design"]["world_assurance"]["transport_count"], 2
        )
        with self.assertRaises(ValueError):
            publish(self.root, source=self.legacy_file, intensity=4,
                    approved_sha256="0" * 64)
        accepted = publish(
            self.root, source=self.legacy_file, intensity=4,
            approved_sha256=drafted["design_sha256"],
        )
        self.assertTrue(accepted["published"])
        self.assertTrue((self.root / accepted["source"]).is_file())
        self.assertTrue(accepted["original_source_preserved"])
        self.assertEqual(
            json.loads((self.root / self.legacy_file).read_text())["director_world"],
            self.base.payload(),
        )
        with self.assertRaises(ValueError):
            publish(self.root, source=self.legacy_file, intensity=4,
                    approved_sha256=drafted["design_sha256"])
        promoted = audit(self.root, source=accepted["source"])
        self.assertTrue(promoted["source_bound"])

    def test_dragon_reconstructs_real_transit_and_admits_reviewed_evidence(self):
        self._start()
        self._step("hero", "transit:ferry")
        self._step("hero", "transit:ferry")
        review = queue(self.root, session="hero")
        report = review["study"]
        self.assertEqual(report["mode_use_counts"]["ferry"], 2)
        self.assertEqual(report["actual_faction_standings"]["council"], 60)
        self.assertEqual(report["actual_passage_use_counts"]["ferry"], 2)
        self.assertTrue(report["world_flags_unlocked"])
        self.assertFalse(report["production_model_weights_trained"])
        with self.assertRaises(ValueError):
            queue(self.root, session="hero", approved_sha256="0" * 64)
        admission = queue(
            self.root, session="hero", approved_sha256=review["study_sha256"])
        self.assertTrue(admission["admitted_to_research_queue"])
        self.assertTrue(Path(admission["path"]).is_file())
        begin(self.root, source=self.dynamic_file, session="other")
        contrasting = compare(self.root, first="hero", second="other")
        self.assertTrue(contrasting["standing_differences"])
        self.assertFalse(contrasting["model_weights_updated"])
        self._step("hero", "wait:wait")
        with self.assertRaises(ValueError):
            queue(self.root, session="hero", approved_sha256=review["study_sha256"])

    def test_cinematic_world_events_are_chained_to_real_action_receipt(self):
        self._start()
        before = inspect(self.root, session="hero")
        after = self._step("hero", "transit:ferry")
        result = delta(self.root, session="hero", before=before, after=after)
        data = result["living_world_events"]
        self.assertEqual(data["transport"]["mode"], "ferry")
        self.assertEqual(data["transport"]["destination"], self.neighbor)
        self.assertEqual(data["standing_changes"][0]["delta"], 30)
        self.assertEqual(data["new_world_flags"], ["charter"])
        forged = dict(before, last_receipt_sha256="0" * 64)
        with self.assertRaises(ValueError):
            delta(self.root, session="hero", before=forged, after=after)

    def test_native_atlas_exposes_factions_and_transport_map(self):
        exported = export(self.root, source=self.dynamic_file)
        directory = Path(exported["path"])
        self.assertTrue((directory / "director_minimap.gd").is_file())
        player = (directory / "director_player.gd").read_text()
        minimap = (directory / "director_minimap.gd").read_text()
        self.assertIn("Persistent world status", player)
        self.assertIn("world_state", player)
        self.assertIn("authored_passages", minimap)
        self.assertTrue(verify(self.root, source=self.dynamic_file)["source_manifest_verified"])

    def test_cli_dynamic_creation_routes_and_research(self):
        drafted = run_game_cli([
            "jeeves", "director-dynamics-design",
            "--project", str(self.root),
            "--source", self.legacy_file, "--intensity", "2",
        ])
        self.assertTrue(drafted["ok"])
        start = run_game_cli([
            "jeeves", "director-session-begin", "--project", str(self.root),
            "--source", self.dynamic_file, "--session", "operator",
        ])
        self.assertTrue(start["ok"])
        advised = run_game_cli([
            "jeeves", "director-route", "--project", str(self.root),
            "--session", "operator", "--destination", self.neighbor,
        ])
        self.assertTrue(advised["ok"])
        evidence = run_game_cli([
            "jeeves", "dragon-world-study", "--project", str(self.root),
            "--session", "operator",
        ])
        self.assertTrue(evidence["ok"])
        blocked = run_game_cli([
            "jeeves", "director-dynamics-publish", "--project", str(self.root),
            "--source", self.legacy_file, "--kind", "unsafe",
        ])
        self.assertFalse(blocked["ok"])


if __name__ == "__main__":
    unittest.main()
