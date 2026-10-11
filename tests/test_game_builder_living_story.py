"""Living world is a second real playable game genre with stateful NPCs/quests."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import json
import random
import re
import shutil
import subprocess
import tempfile
import unittest

from skeleton.ai.game_builder.living_story_runtime import (
    StoryIntent, StoryError, original_story_world, first_story_state, npc_region,
    story_choices, story_step, story_play, story_verify, demonstrate_story,
    dialogue_line, MAX_TURNS,
)
from skeleton.ai.game_builder.living_story_export import (
    StoryExportError, StoryPackage, render_story_package,
)
from skeleton.ai.game_builder.living_story_mirror import (
    StoryMirrorError, review_living_story,
)


class LivingWorldSimulationTests(unittest.TestCase):
    def intent(self, *, mode="postgame", seed=101911, citizens=24,
               regions=7, completion=2):
        return StoryIntent(
            project_id="original-living-rpg-2026",
            title="Willow Reach Chronicles", seed=seed,
            regions=regions, population=citizens,
            mode=mode, quests_to_finish=completion,
        )

    def test_original_world_has_real_npc_schedules_graph_and_quests(self):
        intent = self.intent(citizens=128, regions=12)
        world = original_story_world(intent, authorized=True)
        self.assertEqual(len(world.citizens), 128)
        self.assertEqual(len(world.regions), 12)
        self.assertEqual(len(world.quests), 3)
        self.assertEqual(world.digest, original_story_world(intent, authorized=True).digest)
        self.assertEqual(len({npc.key for npc in world.citizens}), 128)
        npc = world.citizens[0]
        positions = [npc_region(npc, n) for n in range(12)]
        self.assertEqual(positions[0:3], [npc.home] * 3)
        self.assertEqual(positions[3:6], [npc.workplace] * 3)
        self.assertEqual(positions[6:9], [npc.lookout] * 3)
        self.assertEqual(positions[9:12], [npc.home] * 3)
        self.assertTrue(all(region.neighbors for region in world.regions))
        self.assertNotEqual(npc.home, npc.workplace)
        self.assertNotEqual(npc.workplace, npc.lookout)
        self.assertNotEqual(world.citizens[1].faction, world.citizens[0].faction)
        self.assertEqual(world.payload()["schema"], "skeleton.game_builder.living_story.v1")

    def test_all_modes_and_all_branching_endings_replay(self):
        for mode in ("campaign", "postgame", "sandbox"):
            for ending in ("stewardship", "discovery", "independence"):
                with self.subTest(mode=mode, ending=ending):
                    world = original_story_world(self.intent(mode=mode), authorized=True)
                    replay = demonstrate_story(world, authorized=True, ending=ending)
                    story_verify(world, replay, authorized=True)
                    self.assertEqual(replay.final.ending, ending)
                    self.assertGreaterEqual(len(replay.final.completed), 2)
                    self.assertTrue(replay.final.known)
                    self.assertTrue(replay.final.discussed)
                    self.assertEqual(replay.final.status, {
                        "campaign": "won", "postgame": "epilogue",
                        "sandbox": "open"}[mode])
                    self.assertEqual(len(replay.receipts), replay.final.turn)
                    self.assertTrue(all(r.after_digest and r.before_digest
                                        for r in replay.receipts))
                    if mode != "campaign":
                        self.assertTrue(story_choices(world, replay.final))
                        further = story_step(world, replay.final, "wait", authorized=True)
                        self.assertEqual(further.turn, replay.final.turn + 1)
                        self.assertEqual(further.ending, ending)
                        self.assertEqual(further.status, replay.final.status)
                    else:
                        self.assertFalse(story_choices(world, replay.final))

    def test_ending_choices_require_real_matching_faction_quest_proofs(self):
        for ending, required_faction in (
            ("stewardship", "gardeners"),
            ("discovery", "wayfinders"),
            ("independence", "makers"),
        ):
            world = original_story_world(self.intent(
                mode="postgame", completion=1), authorized=True)
            proof = demonstrate_story(world, authorized=True, ending=ending)
            self.assertEqual(proof.final.ending, ending)
            self.assertEqual(len(proof.final.completed), 1)
            completed = next(q for q in world.quests
                             if q.key == proof.final.completed[0])
            self.assertEqual(completed.faction, required_faction)
            before_choice = story_play(
                world, tuple(x.action for x in proof.receipts[:-1]),
                authorized=True).final
            allowed = story_choices(world, before_choice)
            self.assertIn("choose:" + ending, allowed)
            for other in ("stewardship", "discovery", "independence"):
                if other != ending:
                    self.assertNotIn("choose:" + other, allowed)
                    with self.assertRaises(StoryError):
                        story_step(world, before_choice,
                                   "choose:" + other, authorized=True)
            self.assertEqual(before_choice.ending, None)
            self.assertEqual(
                story_step(world, before_choice, "choose:" + ending,
                           authorized=True), proof.final,
            )

    def test_dynamic_dialogue_inventory_reputation_and_time(self):
        world = original_story_world(self.intent(), authorized=True)
        state = first_story_state(world, authorized=True)
        npc = world.citizens[0]
        line = dialogue_line(world, state, npc.key)
        self.assertIn(npc.name, line)
        self.assertIn(world.quests[0].premise, line)
        self.assertIn("talk:"+npc.key, story_choices(world, state))
        state = story_step(world, state, "talk:"+npc.key, authorized=True)
        self.assertIn(world.quests[0].key, state.known)
        self.assertIn(npc.key, state.discussed)
        self.assertNotIn("talk:"+npc.key, story_choices(world, state))
        self.assertIn("wait", story_choices(world, state))
        self.assertEqual(state.turn, 1)
        self.assertEqual(state.score, 0)
        proof = demonstrate_story(world, authorized=True)
        self.assertGreater(proof.final.score, 0)
        self.assertEqual(sum(proof.final.faction_trust), 50)
        self.assertGreaterEqual(len(proof.final.inventory), 0)
        self.assertIn("community thrive", dialogue_line(
            world, proof.final, npc.key))

    def test_high_population_and_large_region_world_still_provable(self):
        for seed in (1, 31, 98127, 574224):
            with self.subTest(seed=seed):
                world = original_story_world(self.intent(
                    seed=seed, citizens=128, regions=12, completion=3), authorized=True)
                proof = demonstrate_story(world, authorized=True)
                self.assertEqual(len(proof.final.completed), 3)
                self.assertLess(len(proof.receipts), 200)
                story_verify(world, proof, authorized=True)

    def test_full_24_original_quest_arcs_npc_roles_and_postgame_progression(self):
        intent = StoryIntent(
            "twenty-four-original-arcs", "Beyond the Old Coast",
            seed=48274, regions=12, population=128,
            mode="postgame", quests_to_finish=24, quest_arcs=24,
        )
        world = original_story_world(intent, authorized=True)
        self.assertEqual(len(world.quests), 24)
        self.assertEqual(len({q.key for q in world.quests}), 24)
        self.assertEqual(len({q.giver for q in world.quests}), 24)
        self.assertEqual(len({q.item for q in world.quests}), 24)
        self.assertEqual(len({q.premise for q in world.quests}), 24)
        self.assertEqual({q.faction for q in world.quests},
                         {"gardeners", "wayfinders", "makers"})
        proof = demonstrate_story(world, authorized=True, ending="discovery")
        story_verify(world, proof, authorized=True)
        self.assertEqual(len(proof.final.completed), 24)
        self.assertEqual(sum(proof.final.faction_trust), 300)
        self.assertEqual(proof.final.ending, "discovery")
        self.assertLess(proof.final.turn, MAX_TURNS)
        self.assertTrue(story_choices(world, proof.final))
        source = render_story_package(world, proof, authorized=True)
        self.assertEqual(source.manifest["npc_count"], 128)
        self.assertEqual(source.manifest["quest_count"], 24)
        self.assertGreater(source.manifest["proof_actions"], 50)
        self.assertTrue(review_living_story(
            world, proof, source, authorized=True, attempts=64).passed)

    def test_state_and_action_forgery_fail_closed(self):
        world = original_story_world(self.intent(mode="campaign"), authorized=True)
        proof = demonstrate_story(world, authorized=True)
        state = first_story_state(world, authorized=True)
        with self.assertRaises(PermissionError):
            story_step(world, state, "wait", authorized=False)
        for command in ("travel:fake", "talk:npc_missing", "resolve:quest_00",
                        "choose:stewardship", "import:untrusted.py", "wait;os.system"):
            with self.subTest(command=command):
                with self.assertRaises(StoryError):
                    story_step(world, state, command, authorized=True)
        for forged in (
            replace(state, world_digest="a"*64),
            replace(state, location="elsewhere"),
            replace(state, score=12),
            replace(state, faction_trust=(99, 0, 0)),
            replace(state, completed=("not-a-quest",)),
            replace(state, inventory=("external-game-asset",)),
            replace(state, ending="discovery"),
        ):
            with self.assertRaises(StoryError):
                story_step(world, forged, "wait", authorized=True)
        with self.assertRaises(StoryError):
            story_step(world, proof.final, "wait", authorized=True)
        with self.assertRaises(StoryError):
            story_verify(world, replace(proof, initial_digest="0"*64), authorized=True)
        with self.assertRaises(StoryError):
            story_verify(world, replace(proof,
                final=replace(proof.final, score=0)), authorized=True)
        row = proof.receipts[0]
        forged = replace(proof, receipts=(
            replace(row, action="travel:unreachable"), *proof.receipts[1:]))
        with self.assertRaises(StoryError):
            story_verify(world, forged, authorized=True)

    def test_input_budgets_and_no_operator(self):
        with self.assertRaises(PermissionError):
            original_story_world(self.intent(), authorized=False)
        with self.assertRaises(StoryError):
            StoryIntent("untrusted", "test", 1, population=129)
        with self.assertRaises(StoryError):
            StoryIntent("untrusted", "test", 1, regions=13)
        with self.assertRaises(StoryError):
            StoryIntent("untrusted", "test", 1, mode="untrusted")
        with self.assertRaises(StoryError):
            StoryIntent("untrusted", "test", True)
        world = original_story_world(self.intent(), authorized=True)
        with self.assertRaises(StoryError):
            story_play(world, tuple("wait" for _ in range(MAX_TURNS+1)),
                       authorized=True)


class LivingStoryExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = original_story_world(StoryIntent(
            "living-native-original", "Echo Terrace Tales", seed=2026,
            regions=7, population=32, mode="postgame", quests_to_finish=2,
        ), authorized=True)
        cls.proof = demonstrate_story(cls.world, authorized=True)
        cls.pkg = render_story_package(cls.world, cls.proof, authorized=True)

    def test_package_is_content_addressed_offline_and_independently_playable(self):
        release = self.pkg.manifest
        self.assertEqual(release["npc_count"], 32)
        self.assertEqual(release["regions"], 7)
        self.assertEqual(release["quest_count"], 3)
        self.assertEqual(release["ending"], "stewardship")
        self.assertEqual(release["mode"], "postgame")
        self.assertIn("index.html", self.pkg.files)
        self.assertIn("godot/scripts/main.gd", self.pkg.files)
        self.assertIn("godot/scenes/main.tscn", self.pkg.files)
        self.assertIn("godot/proof.json", self.pkg.files)
        self.assertEqual(self.pkg.digest, render_story_package(
            self.world, self.proof, authorized=True).digest)
        self.assertEqual(set(self.pkg.files), set(release["files"]) | {"release.json"})
        self.assertEqual(self.pkg.files["release.json"].decode("utf-8"),
            json.dumps(release, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True)+"\n")
        self.assertNotIn("http://", self.pkg.files["index.html"].decode("utf-8"))
        self.assertIn("Content-Security-Policy", self.pkg.files["index.html"].decode("utf-8"))
        self.assertNotIn("https://", self.pkg.files["index.html"].decode("utf-8"))
        self.assertFalse(release["trained_model"])
        self.assertFalse(release["publication_approved"])

    def test_godot_native_script_contains_real_interactive_npc_and_replay_logic(self):
        script = self.pkg.files["godot/scripts/main.gd"].decode("utf-8")
        for item in ("func _choices()", "func _where(", "func _act(",
                     "func _verify()", "STORY_NATIVE_REPLAY_OK",
                     "choose:stewardship", "quest", "trust", "scroll",
                     "func _unhandled_key_input"):
            self.assertIn(item, script)
        proof = json.loads(self.pkg.files["godot/proof.json"])
        self.assertEqual(proof["world_digest"], self.world.digest)
        self.assertEqual(proof["python_replay_digest"], self.proof.digest)
        self.assertEqual(proof["final"], self.proof.final.payload())
        self.assertEqual(proof["actions"],
                         [x.action for x in self.proof.receipts])

    def test_browser_js_syntax_and_static_security(self):
        html = self.pkg.files["index.html"].decode("utf-8")
        scripts = re.findall(r"<script>(.*?)</script>", html, flags=re.DOTALL)
        self.assertEqual(len(scripts), 1)
        self.assertIn("const WORLD=", scripts[0])
        self.assertIn("function available(s)", scripts[0])
        self.assertIn("function play(action)", scripts[0])
        if shutil.which("node"):
            with tempfile.TemporaryDirectory() as temp:
                source = Path(temp) / "original-story.js"
                source.write_text(scripts[0], encoding="utf-8")
                subprocess.run(["node", "--check", str(source)],
                               capture_output=True, check=True, timeout=10)

    def test_mirror_room_executes_128_real_attacks_and_detects_source_tampering(self):
        report = review_living_story(
            self.world, self.proof, self.pkg, authorized=True, attempts=128)
        self.assertTrue(report.passed, [
            p.payload() for p in report.probes if not p.passed])
        self.assertEqual(len(report.probes), 128)
        self.assertEqual(len({p.family for p in report.probes}), 12)
        self.assertEqual(report.digest, review_living_story(
            self.world, self.proof, self.pkg, authorized=True, attempts=128).digest)
        self.assertFalse(report.payload()["copyright_similarity_cleared"])
        with self.assertRaises(PermissionError):
            review_living_story(self.world, self.proof, self.pkg,
                                authorized=False)
        with self.assertRaises(StoryMirrorError):
            review_living_story(self.world, self.proof, self.pkg,
                                authorized=True, attempts=32)
        tampered = dict(self.pkg.files)
        tampered["index.html"] += b"nasty third-party code"
        with self.assertRaises(StoryExportError):
            StoryPackage(tampered, self.pkg.manifest)
        with self.assertRaises(StoryExportError):
            StoryPackage(self.pkg.files,
                         {**self.pkg.manifest, "npc_count": 999})

    def test_story_modes_have_distinct_releases(self):
        digests = set()
        for mode in ("campaign", "postgame", "sandbox"):
            world = original_story_world(replace(self.world.intent, mode=mode),
                                         authorized=True)
            proof = demonstrate_story(world, authorized=True)
            pkg = render_story_package(world, proof, authorized=True)
            mirror = review_living_story(
                world, proof, pkg, authorized=True, attempts=64)
            self.assertTrue(mirror.passed)
            self.assertIn(pkg.manifest["ending"],
                          ("stewardship", "discovery", "independence"))
            digests.add(pkg.digest)
        self.assertEqual(len(digests), 3)


if __name__ == "__main__":
    unittest.main()
