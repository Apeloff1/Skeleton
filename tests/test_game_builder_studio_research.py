"""Full rights-reviewed original-game research -> studio -> mirror -> consumer gates."""
from __future__ import annotations

import json
import unittest

from skeleton.ai.game_builder.original_game_studio import StudioError, run_original_game_studio
from skeleton.ai.game_builder.playable_world import GameBuildIntent
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore
from skeleton.ai.game_builder.rights import RightsLedger
from skeleton.ai.game_builder.knowledge_rights_bridge import ResearchHandoffError
from tests.test_game_builder_knowledge_rights_bridge import record, reviewed


class ResearchToConsumerStudioTests(unittest.TestCase):
    def setUp(self):
        self.library = ReviewedKnowledgeStore(":memory:")
        self.library.import_document(
            reviewed(), expected_parent_digest=None, authorized=True)
        self.brief = self.library.build_brief("studio-one", "jump", authorized=True)
        self.rights = RightsLedger()
        self.rights.register_source(record())
        self.intent = GameBuildIntent(
            project_id="original-rights-cleared-demo",
            title="Novel World and Research",
            subtitle="Sources are design references only, never copied runtime.",
            seed=387, width=11, height=11, levels=1,
            collectibles_per_level=1, hazards_per_level=0,
            theme="space", starting_health=3,
        )

    def tearDown(self):
        self.library.close()

    def run_studio(self, **overrides):
        kwargs = {
            "reviewed_library": self.library,
            "research_brief": self.brief,
            "rights_ledger": self.rights,
            "human_research_approved": True,
        }
        kwargs.update(overrides)
        return run_original_game_studio(
            self.intent, authorized=True, mirror_attempts=64,
            companion_practice_games=0, **kwargs,
        )

    def test_independently_cleared_research_enters_original_to_product_chain(self):
        run = self.run_studio()
        self.assertEqual(run.source, "original-research-referenced")
        self.assertEqual(run.stages[0].name, "reviewed_research")
        self.assertEqual(run.stages[-1].name, "consumer_source_candidate")
        self.assertTrue(run.mirror.passed)
        self.assertIsNotNone(run.project.cleared_research)
        cleared = run.project.cleared_research.to_payload()
        self.assertEqual(
            cleared["packet_digest"],
            run.package.manifest["research_clearance_digest"],
        )
        pipeline = json.loads(run.package.files["studio/pipeline.json"])
        self.assertTrue(pipeline["rights_reference_only"])
        self.assertEqual(pipeline["research_packet_digest"],
                         cleared["packet_digest"])
        self.assertEqual(len(run.mirror.probes), 64)
        self.assertIn("Reviewed research context", run.package.files["index.html"].decode("utf-8"))
        self.assertNotIn("Jump timing is predictable",
                         run.package.files["godot/scripts/main.gd"].decode("utf-8"))
        self.assertFalse(run.consumer.rights_reviewed)
        self.assertFalse(run.consumer.approved_for_publication)
        request_tools = [r.tool_id for r in run.tool_plan.requests]
        self.assertEqual(request_tools[:2], ["knowledge.search", "rights.check"])
        self.assertEqual(run.project.proof.final_state.status, "won")

    def test_research_requires_all_four_independent_inputs(self):
        with self.assertRaises(StudioError):
            self.run_studio(human_research_approved=False)
        with self.assertRaises(StudioError):
            self.run_studio(rights_ledger=None)
        with self.assertRaises(StudioError):
            self.run_studio(research_brief=None)
        with self.assertRaises(StudioError):
            self.run_studio(reviewed_library=None)
        with self.assertRaises(StudioError):
            run_original_game_studio(
                self.intent, authorized=True,
                human_research_approved=True,
                companion_practice_games=0, mirror_attempts=64,
            )

    def test_missing_licensed_source_stops_before_packaging(self):
        clean = RightsLedger()
        with self.assertRaises(ResearchHandoffError):
            self.run_studio(rights_ledger=clean)
        self.assertEqual(clean.snapshot()["decisions"], [])

    def test_authored_tiles_do_not_inherit_unreviewed_research_rights(self):
        from skeleton.ai.game_builder.playable_compiler import compile_original_game
        original = compile_original_game(self.intent, authorized=True)
        authored = [list(level.rows) for level in original.world.levels]
        with self.assertRaises(StudioError):
            self.run_studio(
                human_reviewed_tiles=authored, human_authored_approved=True,
            )


if __name__ == "__main__":
    unittest.main()
