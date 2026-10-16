"""Specialized tests: original NPC/commerce engine and causal Dragon learning.

Run explicitly:
    python -m unittest tests.test_jeeves_director_society

Legacy worlds must retain their original digests. No global CI workflow,
dangerous action, personal sentiment, licensed assets or checkpoint weights
are introduced by these tests.
"""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.quest_scene_forge import (
    forge_director, compile_director_blueprint,
)
from skeleton.ai.game_builder.quest_scene_engine import (
    DirectorAction, director_initial, director_step, available_director_actions,
)
from skeleton.ai.game_builder.quest_world_dynamics import (
    Gate, Requirements, WorldDynamics,
)
from skeleton.ai.game_builder.quest_society import (
    Resident, Good, Shop, SocietyRules, TrustRequirement, compile_society,
    phase, residents_here,
)
from skeleton.developer.game_cli import SCHEMA as GAME_SCHEMA, run_game_cli
from skeleton.developer.jeeves_game_director_society_author import preview, publish
from skeleton.developer.jeeves_game_director_society_audit import audit
from skeleton.developer.jeeves_game_dragon_society import (
    study, queue, compare,
)
from skeleton.developer.jeeves_game_director_session import begin, inspect, choose, _load
from skeleton.developer.jeeves_game_director_labyrinth import plan
from skeleton.developer.jeeves_game_director_atlas import export, verify
from skeleton.developer.jeeves_game_director_causality import audit as causal_audit
from skeleton.developer.jeeves_game_director_events import delta
from skeleton.developer.jeeves_game_director_society_stress import stress
from skeleton.developer.jeeves_game_dragon_policy import _context


class OriginalSocietyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "original_game"
        self.root.mkdir()
        (self.root / "design").mkdir()
        (self.root / "skeleton.game.json").write_text(json.dumps({
            "schema": GAME_SCHEMA,
            "name": "original_game",
            "vision": "New original society with merchants, companions and routes",
            "era": "extraction_now", "archetype": "auto",
        }))
        self.base = forge_director(
            "original_game", seed=81,
            regions=("harbor", "garden", "library", "tower"),
            quest_types=("main_story", "investigation"), stages=2,
        )
        self.original_file = "design/director_campaign_source.json"
        self._save(self.original_file, self.base)
        proposal = preview(self.root, source=self.original_file, intensity=2)
        self.assertTrue(proposal["ok"])
        self.design = proposal
        self.social_world = compile_director_blueprint(
            proposal["design"]["candidate"]["director_world"],
            human_reviewed=True,
        )
        self.society = self.social_world.dynamics.society
        self.npc = self.society.residents[0]
        self.shop = self.society.shops[0]
        self.item = self.shop.goods[0]
        self.passages = {
            passage.key: passage for passage in self.social_world.dynamics.passages
        }
        self.ticket_passage = next(
            passage for passage in self.passages.values()
            if passage.consume_item == self.item.key
        )
        self.trusted_passage = next(
            passage for passage in self.passages.values()
            if passage.requirements.trust
        )
        self.dynamic_file = "design/director_society_test_source.json"
        self._save(self.dynamic_file, self.social_world)

    def _save(self, name, world):
        (self.root / name).write_text(json.dumps({
            "schema": "skeleton.jeeves.director_campaign_source.v1",
            "director_world": world.payload(), "author_review_acknowledged": True,
        }))

    def _begin(self, session="hero", source=None):
        return begin(
            self.root, source=source or self.dynamic_file, session=session,
        )

    def _do(self, action, session="hero"):
        before = inspect(self.root, session=session)
        return choose(
            self.root, session=session, choice=action,
            expected_sequence=before["sequence"],
            expected_state_sha256=before["current_state_sha256"],
        )

    def _reach_next_conversation(self, session="hero"):
        for _ in range(9):
            offered = {
                item["choice"] for item in inspect(self.root, session=session)["actions"]
            }
            if "speak:" + self.npc.key in offered:
                return
            self._do("rest:rest", session=session)
        self.fail("authored NPC never becomes available after advancing clock")

    def test_exact_original_world_hashes_and_old_actions_unchanged(self):
        compiled = compile_director_blueprint(
            self.base.payload(), human_reviewed=True,
        )
        self.assertEqual(compiled.digest, self.base.digest)
        self.assertEqual(compiled.payload(), self.base.payload())
        state = director_initial(self.base)
        self.assertNotIn("world_state", state.payload())
        self.assertNotIn("society", compiled.payload())
        start = self._begin("legacy", self.original_file)
        self.assertNotIn("society", start)
        self.assertNotIn("world_state", start)
        self.assertNotIn("rest:rest", {
            row["choice"] for row in start["actions"]
        })
        self._do("wait:wait", session="legacy")
        self.assertEqual(inspect(self.root, session="legacy")["sequence"], 1)

    def test_NPC_arrival_changes_with_authored_time_not_wall_clock(self):
        start = self._begin()
        self.assertEqual(start["society"]["calendar"]["phase"], "dawn")
        self.assertIn(self.npc.key, {
            entry["key"] for entry in start["society"]["present_residents"]
        })
        self.assertIn("speak:" + self.npc.key,
                      {a["choice"] for a in start["actions"]})
        before = start["world_state"]["society"]
        self._do("rest:rest")
        now = inspect(self.root, session="hero")
        self.assertEqual(now["society"]["calendar"]["phase"], "day")
        self.assertEqual(now["world_state"]["society"]["shop_stock"],
                         before["shop_stock"])
        self.assertEqual(now["society"]["wallet"],
                         self.society.starting_balance)
        self.assertEqual(_load(self.root, name="hero")[5], 1)

    def test_dialogue_trust_is_persistent_per_cycle_and_can_unlock_routes(self):
        start = self._begin()
        self.assertEqual(start["society"]["relationships"][0][1],
                         self.npc.initial_trust)
        first = self._do("speak:" + self.npc.key)
        self.assertGreater(
            dict(first["society"]["relationships"])[self.npc.key],
            self.npc.initial_trust)
        with self.assertRaises(ValueError):
            self._do("speak:" + self.npc.key)
        before = _context(_load(self.root, name="hero")[2])
        for _ in range(4):
            self._reach_next_conversation()
            self._do("speak:" + self.npc.key)
            score = dict(inspect(self.root, session="hero")["society"]["relationships"])
            if score[self.npc.key] >= 40:
                break
        state = inspect(self.root, session="hero")
        self.assertGreaterEqual(
            dict(state["society"]["relationships"])[self.npc.key], 40)
        self.assertTrue(any(a["choice"] == "transit:" + self.trusted_passage.key
                            for a in state["actions"]))
        self.assertIn(self.npc.unlock_world_flag,
                      state["world_state"]["world_flags"])
        self.assertNotEqual(_context(_load(self.root, name="hero")[2]), before)
        self.assertGreater(state["sequence"], 2)

    def test_branching_dialogue_choices_affect_trust_and_authored_story_flags(self):
        self._begin()
        self.assertGreaterEqual(len(self.npc.dialogue), 2)
        option = next(c for c in self.npc.dialogue if c.key == "offer_help")
        rejected = next(c for c in self.npc.dialogue if c.key == "question_motives")
        before = inspect(self.root, session="hero")
        self.assertIn("discuss:" + self.npc.key + "_" + option.key,
                      {a["choice"] for a in before["actions"]})
        self.assertNotIn(option.response, str(before["society"]))
        after = self._do("discuss:" + self.npc.key + "_" + option.key)
        self.assertEqual(
            dict(after["society"]["relationships"])[self.npc.key],
            self.npc.initial_trust + option.trust_delta,
        )
        self.assertIn(option.grant_world_flag, after["world_state"]["world_flags"])
        self.assertTrue(option.once)
        self.assertIn([self.npc.key, option.key, 1],
                      after["society"]["canonical_dialogue_history"])
        presentation = delta(self.root, session="hero", before=before, after=after)
        spoken = presentation["living_world_events"]["society"]["authored_dialogue"]
        self.assertEqual(spoken["line"], option.response)
        self.assertEqual(spoken["player_prompt"], option.prompt)
        self.assertEqual(spoken["resident"], self.npc.key)
        with self.assertRaises(ValueError):
            self._do("discuss:" + self.npc.key + "_" + rejected.key)
        self._reach_next_conversation()
        offered = {x["choice"] for x in inspect(
            self.root, session="hero")["actions"]}
        self.assertNotIn("discuss:" + self.npc.key + "_" + option.key, offered)
        self.assertIn("discuss:" + self.npc.key + "_" + rejected.key, offered)
        second = self._do("discuss:" + self.npc.key + "_" + rejected.key)
        trust = dict(second["society"]["relationships"])[self.npc.key]
        self.assertEqual(
            trust, self.npc.initial_trust + option.trust_delta
                   + rejected.trust_delta,
        )
        self.assertIn(option.grant_world_flag, second["world_state"]["world_flags"])
        observed = study(self.root, session="hero")
        self.assertEqual(observed["dialogue_topic_selection_counts"][
            self.npc.key + ":" + option.key], 1)
        self.assertEqual(observed["dialogue_topic_selection_counts"][
            self.npc.key + ":" + rejected.key], 1)
        causal = causal_audit(self.root, session="hero")
        self.assertEqual(causal["summary"]["NPC_conversation_counts"][self.npc.key], 2)

    def test_real_buy_sell_changes_wallet_stock_and_canonical_inventory(self):
        beginning = self._begin()
        self.assertEqual(beginning["society"]["wallet"],
                         self.society.starting_balance)
        key = self.shop.key + "_" + self.item.key
        first = self._do("buy:" + key)
        self.assertEqual(first["society"]["wallet"],
                         self.society.starting_balance - self.item.buy_price)
        self.assertEqual(dict(first["society"]["owned_goods"])[self.item.key], 1)
        self.assertIn(self.item.key, first["acquired"])
        shop = first["society"]["open_merchants"][0]["products"][0]
        self.assertEqual(shop["stock"], self.item.starting_stock - 1)
        sold = self._do("sell:" + key)
        self.assertEqual(
            sold["society"]["wallet"],
            first["society"]["wallet"] + self.item.sell_price)
        self.assertNotIn(self.item.key, sold["acquired"])
        self.assertEqual(sold["society"]["owned_goods"], [])
        self.assertEqual(
            sold["society"]["open_merchants"][0]["products"][0]["stock"],
            self.item.starting_stock)
        self.assertEqual(sold["sequence"], 2)
        with self.assertRaises(ValueError):
            self._do("sell:" + key)
        self.assertEqual(_load(self.root, name="hero")[2].digest,
                         _load(self.root, name="hero")[2].digest)

    def test_schedules_market_routes_and_shop_goods_are_source_bound(self):
        self.assertEqual(compile_society(self.society.payload()), self.society)
        self.assertTrue(self.trusted_passage.requirements.trust)
        self.assertEqual(self.ticket_passage.consume_item, self.item.key)
        self.assertNotIn(self.item.key, {
            a.produces for scene in self.base.scenes
            for a in scene.affordances
        })
        status = self._begin()
        self.assertIn("buy:" + self.shop.key + "_" + self.item.key,
                      {a["choice"] for a in status["actions"]})
        self.assertNotIn("transit:" + self.ticket_passage.key,
                         {a["choice"] for a in status["actions"]})
        self._do("buy:" + self.shop.key + "_" + self.item.key)
        now = inspect(self.root, session="hero")
        self.assertIn("transit:" + self.ticket_passage.key,
                      {a["choice"] for a in now["actions"]})
        next_state = self._do("transit:" + self.ticket_passage.key)
        self.assertEqual(next_state["scene"], self.ticket_passage.destination)
        self.assertNotIn(self.item.key, next_state["acquired"])
        self.assertEqual(next_state["society"]["owned_goods"], [])
        self.assertEqual(
            next_state["world_state"]["passage_uses"],
            [[self.ticket_passage.key, 1]],
        )

    def test_social_planner_finds_source_legally_locked_market_ticket(self):
        from skeleton.ai.game_builder.quest_world_dynamics import Gate
        requirements = Requirements(
            trust=(TrustRequirement(self.npc.key, 40, 100),),
        )
        origin = self.base.starting_scene
        opening = next(s for s in self.base.scenes if s.key == origin)
        fenced = replace(
            self.social_world.dynamics,
            gates=tuple(Gate(
                source=origin, destination=dest,
                requirements=requirements, label="Trust-controlled entry"
            ) for dest in opening.links),
        )
        restricted = replace(self.social_world, dynamics=fenced)
        source = "design/director_social_fenced.json"
        self._save(source, restricted)
        self._begin(source=source)
        before = inspect(self.root, session="hero")
        self.assertFalse(any(a["kind"] in {"travel", "transit"}
                             for a in before["actions"]))
        route = plan(
            self.root, session="hero",
            destination=self.ticket_passage.destination,
            profile="fastest", alternatives=2,
        )
        self.assertTrue(route["faction_and_resource_states_simulated"])
        self.assertTrue(route["routes"])
        first = route["routes"][0]
        self.assertEqual(first["social_and_market_actions"][0],
                         "buy:" + self.shop.key + "_" + self.item.key)
        self.assertIn("transit:" + self.ticket_passage.key, first["actions"])
        self.assertGreater(first["turn_cost"], 1)
        state = _load(self.root, name="hero")[2]
        for leg in first["actions"]:
            kind, key = leg.split(":", 1)
            action = DirectorAction(kind, key, state.scene)
            self.assertIn(action, available_director_actions(restricted, state))
            state = director_step(restricted, state, action)
        self.assertEqual(state.digest, first["expected_arrival_state_sha256"])
        self.assertEqual(before["sequence"], 0)
        self.assertEqual(inspect(self.root, session="hero")["sequence"], 0)

    def test_schema_rejects_unsafe_NPC_shops_and_unearned_trust(self):
        payload = self.society.payload()
        payload["residents"][0]["schedule"][0] = "../../outside"
        with self.assertRaises(ValueError):
            compile_society(payload)
        payload = self.society.payload()
        payload["shops"][0]["goods"][0]["sell_price"] = 999999
        with self.assertRaises(ValueError):
            compile_society(payload)
        payload = self.society.payload()
        payload["shops"][0]["unexpected_script"] = "os.system('oops')"
        with self.assertRaises(ValueError):
            compile_society(payload)
        with self.assertRaises(ValueError):
            TrustRequirement("missing_npc", at_least=120)
        with self.assertRaises(ValueError):
            Shop("unsafe", "absent", "scene_1", "Merchant", ())
        with self.assertRaises(ValueError):
            Resident(
                "out", "Invalid person", None,
                ("scene_a", "scene_a", "scene_a", "scene_a"),
                "Hello", trust_gain=True,
            )

    def test_preview_manual_approval_and_create_only_revision(self):
        self.assertEqual(self.design["filesystem_writes"], 0)
        self.assertFalse(self.design["design"]["candidate"]["author_review_acknowledged"])
        with self.assertRaises(ValueError):
            publish(self.root, source=self.original_file, intensity=2,
                    approved_sha256="0" * 64)
        accepted = publish(
            self.root, source=self.original_file, intensity=2,
            approved_sha256=self.design["design_sha256"],
        )
        self.assertTrue(accepted["published"])
        self.assertTrue(accepted["author_has_approved_exact_source_digest"])
        self.assertTrue(
            json.loads((self.root / accepted["source"]).read_text())
            ["author_review_acknowledged"]
        )
        with self.assertRaises(ValueError):
            publish(
                self.root, source=self.original_file, intensity=2,
                approved_sha256=self.design["design_sha256"],
            )
        self.assertEqual(
            json.loads((self.root / self.original_file).read_text())
            ["director_world"], self.base.payload(),
        )

    def test_causal_and_dragon_studies_are_replay_grounded(self):
        self._begin()
        self._do("speak:" + self.npc.key)
        self._do("buy:" + self.shop.key + "_" + self.item.key)
        report = study(self.root, session="hero")
        self.assertEqual(report["talk_count_by_resident"][self.npc.key], 1)
        self.assertEqual(report["buy_count_by_shop_good"][
            self.shop.key + "_" + self.item.key], 1)
        self.assertEqual(report["money_spent_on_real_actions"], self.item.buy_price)
        self.assertFalse(report["player_satisfaction_inferred"])
        self.assertFalse(report["real_model_training_performed"])
        causal = causal_audit(self.root, session="hero")
        self.assertEqual(causal["summary"]["society_actions_replayed"], 2)
        self.assertEqual(causal["summary"]["shop_currency_spent"], self.item.buy_price)
        with self.assertRaises(ValueError):
            queue(self.root, session="hero", approved_sha256="0" * 64)
        digest = queue(self.root, session="hero")
        adopted = queue(
            self.root, session="hero", approved_sha256=digest["study_sha256"])
        self.assertTrue(Path(adopted["path"]).is_file())
        self.assertTrue(adopted["admitted_for_training_review"])
        self.assertFalse(adopted["production_weights_updated"])
        self._do("sell:" + self.shop.key + "_" + self.item.key)
        with self.assertRaises(ValueError):
            queue(self.root, session="hero", approved_sha256=digest["study_sha256"])
        self._begin("alternative")
        compared = compare(self.root, first="hero", second="alternative")
        self.assertTrue(compared["trust_differences"])
        self.assertFalse(compared["model_weights_changed"])

    def test_live_society_audit_and_native_UI_source_integrity(self):
        summary = audit(self.root, source=self.dynamic_file)
        self.assertTrue(summary["ok"])
        self.assertEqual(summary["analysis"]["NPC_count"],
                         len(self.society.residents))
        self.assertEqual(summary["analysis"]["shop_count"],
                         len(self.society.shops))
        self.assertFalse(summary["analysis"]["physical_engine_performance_verified"])
        project = export(self.root, source=self.dynamic_file)
        verified = verify(self.root, source=self.dynamic_file)
        self.assertTrue(verified["source_manifest_verified"])
        place = Path(project["path"])
        actor = (place / "director_stage.gd").read_text()
        client = (place / "director_player.gd").read_text()
        self.assertIn("update_scheduled_residents", actor)
        self.assertIn("scheduled_residents", actor)
        self.assertIn("NPC world-time", client)
        self.assertIn("Market:", client)
        self.assertIn("Gold balance:", client)

    def test_repeatable_adversarial_economy_and_character_stress(self):
        previous = self.root / ".jeeves"
        self.assertFalse(previous.exists())
        report = stress(self.root, source=self.dynamic_file, routes=4, intensity=1)
        self.assertTrue(report["ok"])
        self.assertTrue(report["all_market_money_conserved"])
        self.assertEqual(report["total_verified_actions"], 4 * 48)
        self.assertEqual(len(report["scenario_reports"]), 4)
        for scenario in report["scenario_reports"]:
            self.assertTrue(scenario["independent_replay_matches"])
            self.assertEqual(scenario["gameplay_receipt_count"], 48)
            self.assertLessEqual(scenario["final_wallet"],
                                 scenario["initial_wallet"])
            self.assertTrue(scenario["shop_conservation_invariants_verified"])
        self.assertFalse(previous.exists())
        repeat = stress(self.root, source=self.dynamic_file, routes=4, intensity=1)
        self.assertEqual(report, repeat)
        with self.assertRaises(ValueError):
            stress(self.root, source=self.dynamic_file, routes=0)
        with self.assertRaises(ValueError):
            stress(self.root, source=self.dynamic_file, intensity=6)

    def test_CLI_review_and_society_journal_routing(self):
        design = run_game_cli([
            "jeeves", "director-society-design", "--project", str(self.root),
            "--source", self.original_file, "--intensity", "2",
        ])
        self.assertTrue(design["ok"])
        verified = run_game_cli([
            "jeeves", "director-society-audit", "--project", str(self.root),
            "--source", self.dynamic_file,
        ])
        self.assertTrue(verified["ok"])
        self._begin("user")
        evidence = run_game_cli([
            "jeeves", "dragon-society-study", "--project", str(self.root),
            "--session", "user",
        ])
        self.assertTrue(evidence["ok"])
        rejected = run_game_cli([
            "jeeves", "dragon-society-study", "--project", str(self.root),
            "--session", "user", "--kind", "ignored",
        ])
        self.assertFalse(rejected["ok"])


if __name__ == "__main__":
    unittest.main()
