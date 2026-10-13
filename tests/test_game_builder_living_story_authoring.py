"""Full custom human-authored NPC, schedule and quest editor-to-consumer testing."""
from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.living_story_runtime import (
    StoryIntent, original_story_world, demonstrate_story, story_verify,
)
from skeleton.ai.game_builder.living_story_authoring import (
    StoryAuthoringError, compile_authored_story, read_story_blueprint,
    blueprint_document, derive_original_story_intent,
)
from skeleton.ai.game_builder.living_story_blueprint_cli import main as template_main
from skeleton.ai.game_builder.original_game_studio_cli import main as studio_main
from skeleton.ai.game_builder.original_game_studio import run_original_game_studio
from skeleton.ai.game_builder.playable_world import GameBuildIntent


class OriginalLivingStoryAuthoringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = GameBuildIntent(
            project_id="custom-original-npc-story",
            title="Silver Garden World",
            subtitle="Fully custom NPCs and lore in original source.",
            seed=3391, width=11, height=11, levels=1,
            collectibles_per_level=1, hazards_per_level=1,
            theme="ocean", starting_health=4,
        )
        cls.story_intent = derive_original_story_intent(
            cls.base, population=24, regions=7, mode="postgame",
            quests=2, authorized=True)
        cls.reference = original_story_world(cls.story_intent, authorized=True)
        cls.document = blueprint_document(cls.reference, authorized=True)

    def test_custom_npc_story_events_and_regions_are_truly_simulated(self):
        doc = json.loads(json.dumps(self.document))
        doc["citizens"][0]["name"] = "Original Citizen Tessa"
        doc["citizens"][0]["role"] = "lighthouse keeper"
        doc["citizens"][0]["temperament"] = "gentle"
        doc["citizens"][0]["workplace"] = "region_04"
        doc["regions"][0]["name"] = "Blueberry Lantern Commons"
        doc["regions"][0]["atmosphere"] = "floating lanterns in quiet morning mist"
        doc["quests"][0]["premise"] = "Protect the ancient lantern seeds"
        doc["quests"][0]["reward"] = 33
        original = compile_authored_story(
            self.story_intent, doc, authorized=True, human_reviewed=True)
        self.assertNotEqual(original.world.digest, self.reference.digest)
        self.assertEqual(original.world.citizens[0].name, "Original Citizen Tessa")
        self.assertEqual(original.world.citizens[0].workplace, "region_04")
        self.assertEqual(original.world.quests[0].reward, 33)
        witness = demonstrate_story(original.world, authorized=True)
        story_verify(original.world, witness, authorized=True)
        self.assertIn("quest_00", witness.final.completed)
        self.assertEqual(witness.final.score, 33 + self.reference.quests[1].reward)
        self.assertTrue(original.evidence()["original_human_reviewed_text"])
        self.assertFalse(original.evidence()["legally_cleared_for_publication"])
        self.assertFalse(original.evidence()["scripts_imported"])

    def test_editor_template_to_reviewed_consumer_game_cli(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            intent_path = base / "intent.json"
            intent_path.write_text(json.dumps(self.base.to_payload()), encoding="utf-8")
            blueprint = base / "living-world.json"
            args = ["--intent", str(intent_path), "--output", str(blueprint),
                    "--npcs", "24", "--regions", "7", "--mode", "postgame",
                    "--quests", "2", "--trusted-local-operator"]
            result = io.StringIO()
            with redirect_stdout(result):
                self.assertEqual(template_main(args), 0)
            self.assertEqual(json.loads(result.getvalue())["npcs"], 24)
            world = json.loads(blueprint.read_text(encoding="utf-8"))
            world["citizens"][0]["name"] = "The Watcher of Poppy Dock"
            world["quests"][0]["premise"] = "Restore the watcher's original music box"
            blueprint.write_text(json.dumps(world), encoding="utf-8")
            output = base / "consumer"
            studio_args = [
                "--intent", str(intent_path), "--output", str(output),
                "--living-world-npcs", "24", "--living-world-regions", "7",
                "--living-world-blueprint", str(blueprint),
                "--living-world-human-reviewed", "--companion-practice", "0",
                "--mirror-attempts", "64", "--trusted-local-operator",
            ]
            trace = io.StringIO()
            with redirect_stdout(trace):
                self.assertEqual(studio_main(studio_args), 0)
            result = json.loads(trace.getvalue())
            self.assertEqual(result["living_world_npcs"], 24)
            evidence = json.loads((output / "studio/living_story_authoring.json").read_text())
            self.assertTrue(evidence["original_human_reviewed_text"])
            self.assertEqual(evidence["world_digest"], result["living_world_manifest_digest"]
                             and json.loads((output / "living_story/release.json").read_text())["world_digest"])
            self.assertTrue((output / "living_story/index.html").is_file())
            self.assertTrue((output / "living_story/godot/proof.json").is_file())
            self.assertEqual(json.loads((output / "living_story/world.json").read_text())[
                "citizens"][0]["name"], "The Watcher of Poppy Dock")
            self.assertEqual(len(json.loads((output / "studio/living_story_mirror.json").read_text())[
                "probes"]), 128)
            self.assertFalse(result["publication_authorized"])

    def test_cannot_skip_author_review_or_reuse_world_between_projects(self):
        with self.assertRaises(StoryAuthoringError):
            compile_authored_story(
                self.story_intent, self.document, authorized=True,
                human_reviewed=False,
            )
        with self.assertRaises(PermissionError):
            compile_authored_story(
                self.story_intent, self.document, authorized=False,
                human_reviewed=True,
            )
        other = replace(self.story_intent, seed=self.story_intent.seed + 1)
        with self.assertRaisesRegex(StoryAuthoringError, "identity"):
            compile_authored_story(other, self.document,
                                   human_reviewed=True, authorized=True)

    def test_fail_closed_on_script_extras_duplicate_keys_and_unplayable_graph(self):
        invalids = []
        malicious = json.loads(json.dumps(self.document))
        malicious["scripts"] = ["import untrusted; execute()"]
        invalids.append(malicious)
        wrong = json.loads(json.dumps(self.document))
        wrong["quests"][0]["giver"] = "npc_bad"
        invalids.append(wrong)
        unconnected = json.loads(json.dumps(self.document))
        unconnected["regions"][0]["neighbors"] = ["region_02"]
        invalids.append(unconnected)
        oversized = json.loads(json.dumps(self.document))
        oversized["citizens"][0]["name"] = "x" * 1000
        invalids.append(oversized)
        duplicate_quest = json.loads(json.dumps(self.document))
        duplicate_quest["quests"][1]["item"] = duplicate_quest["quests"][0]["item"]
        invalids.append(duplicate_quest)
        for payload in invalids:
            with self.subTest(extra=list(set(payload) - set(self.document))):
                with self.assertRaises(StoryAuthoringError):
                    compile_authored_story(self.story_intent, payload,
                                           human_reviewed=True, authorized=True)
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "blueprint.json"
            p.write_text('{"schema":"x","schema":"y"}', encoding="utf-8")
            with self.assertRaises(StoryAuthoringError):
                read_story_blueprint(self.story_intent, p,
                                     human_reviewed=True, authorized=True)
            p.write_bytes(b"x" * 180001)
            with self.assertRaises(StoryAuthoringError):
                read_story_blueprint(self.story_intent, p,
                                     human_reviewed=True, authorized=True)


if __name__ == "__main__":
    unittest.main()
