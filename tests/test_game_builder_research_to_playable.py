"""End-to-end: independently reviewed research -> actual original playable game."""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import unittest

from skeleton.ai.game_builder.playable_compiler import (
    PlayableCompilationError,
    compile_game_from_reviewed_research,
    compile_original_game,
)
from skeleton.ai.game_builder.playable_world import GameBuildIntent
from skeleton.ai.game_builder.knowledge_rights_bridge import (
    ResearchHandoffError, require_cleared_research_current,
)
from skeleton.ai.game_builder.reviewed_knowledge import (
    ReviewedDocument, ReviewedKnowledgeStore, ReviewedNote,
)
from skeleton.ai.game_builder.rights import RightsLedger

from tests.test_game_builder_knowledge_rights_bridge import record, reviewed


def intent(**changes):
    values = dict(
        project_id="original-game-001",
        title="Original Level Adventure",
        subtitle="Original puzzle game built after research review",
        seed=83,
        levels=2, width=15, height=11,
        collectibles_per_level=2, hazards_per_level=4,
        theme="forest", starting_health=3,
    )
    values.update(changes)
    return GameBuildIntent(**values)


class ResearchGameBuildTests(unittest.TestCase):
    def setUp(self):
        self.library = ReviewedKnowledgeStore(":memory:")
        self.first = self.library.import_document(
            reviewed(), expected_parent_digest=None, authorized=True,
        )
        self.brief = self.library.build_brief("studio-one", "jump", authorized=True)
        self.rights = RightsLedger()
        self.rights.register_source(record())

    def tearDown(self):
        self.library.close()

    def compile(self, *, brief=None, rights=None, intent_value=None,
                human_approved=True, authorized=True):
        return compile_game_from_reviewed_research(
            self.library,
            brief or self.brief,
            rights or self.rights,
            intent_value or intent(),
            human_approved=human_approved,
            authorized=authorized,
        )

    def test_real_game_with_provenance_bound_research(self):
        project = self.compile()
        self.assertIsNotNone(project.cleared_research)
        self.assertEqual(project.proof.final_state.status, "won")
        self.assertEqual(project.playable.world_digest, project.world.digest)
        self.assertEqual(project.cleared_research.artifact_digest, project.world.digest)
        self.assertEqual(
            project.cleared_research.project_id, project.world.intent.project_id,
        )
        manifest = project.receipt()
        self.assertEqual(manifest["research_clearance_digest"],
                         project.cleared_research.to_payload()["packet_digest"])
        self.assertTrue(manifest["rights_reference_only"])
        self.assertTrue(manifest["validated_gameplay_proof"])
        self.assertFalse(manifest["publication_authority"])
        self.assertIn("Reviewed research context", project.playable.html)
        self.assertIn("https://example.org/authorized-study", project.playable.html)
        self.assertIn("Jump timing is predictable", project.playable.html)
        require_cleared_research_current(
            project.cleared_research, self.library, self.rights, authorized=True,
        )

    def test_source_text_never_becomes_rules_or_executable_code(self):
        game = self.compile()
        original = compile_original_game(intent(), authorized=True)
        self.assertEqual(game.world, original.world)
        self.assertEqual(game.proof.digest, original.proof.digest)
        self.assertNotEqual(game.playable.html_sha256, original.playable.html_sha256)

    def test_human_approval_cannot_be_inferred_from_json(self):
        with self.assertRaises(PlayableCompilationError):
            self.compile(human_approved=False)
        self.assertEqual(self.rights.snapshot()["decisions"], [])
        with self.assertRaises(PermissionError):
            self.compile(authorized=False)

    def test_missing_independent_rights_authority_blocks_build(self):
        ledger = RightsLedger()
        with self.assertRaises(ResearchHandoffError):
            self.compile(rights=ledger)
        self.assertEqual(ledger.snapshot()["decisions"], [])

    def test_source_digest_mismatch_blocks_research_integration(self):
        ledger = RightsLedger()
        ledger.register_source(record(digest="0" * 64))
        with self.assertRaises(ResearchHandoffError):
            self.compile(rights=ledger)
        self.assertEqual(ledger.snapshot()["decisions"], [])

    def test_source_license_mismatch_blocks_research_integration(self):
        ledger = RightsLedger()
        ledger.register_source(record(license_id="unrelated-license"))
        with self.assertRaises(ResearchHandoffError):
            self.compile(rights=ledger)

    def test_erasure_prevents_stale_research_compilation(self):
        self.assertTrue(self.compile().proof.final_state.status == "won")
        self.library.erase_owner("studio-one", authorized=True)
        with self.assertRaises(ValueError):
            self.compile()

    def test_retracted_revision_prevents_new_research_build(self):
        self.library.import_document(
            replace(
                reviewed(), text="", notes=(), approved=False,
                status="retracted", observed_at="2026-10-09T12:00:00Z",
            ),
            expected_parent_digest=self.first.revision_digest,
            authorized=True,
        )
        with self.assertRaises(ValueError):
            self.compile()

    def test_wrong_project_packet_cannot_be_rendered(self):
        result = self.compile()
        from skeleton.ai.game_builder.playable_export import (
            PlayableExportError, render_playable_world,
        )
        other = compile_original_game(
            intent(project_id="other-project"), authorized=True,
        )
        with self.assertRaises(PlayableExportError):
            render_playable_world(
                other.world, research_packet=result.cleared_research, authorized=True,
            )

    def test_research_excerpt_with_markup_is_escaped(self):
        payload = reviewed()
        marker = '<img src=x onerror="alert(1)">'
        poisoned = replace(
            payload,
            notes=(replace(payload.notes[0], statement="Jump: " + marker),),
        )
        source = self.library.import_document(
            replace(poisoned, source_id="other-observation",
                    observed_at="2026-10-08T13:00:00Z"),
            expected_parent_digest=None, authorized=True,
        )
        updated_brief = self.library.build_brief("studio-one", "jump", authorized=True)
        ledger = RightsLedger()
        ledger.register_source(record())
        ledger.register_source(record(source_id="other-observation"))
        game = self.compile(brief=updated_brief, rights=ledger)
        self.assertIn("&lt;img", game.playable.html)
        self.assertNotIn(marker, game.playable.html)
        self.assertEqual(game.proof.final_state.status, "won")

    def test_reference_only_source_cannot_grant_model_training(self):
        compiled = self.compile()
        packet = compiled.cleared_research.to_payload()
        self.assertFalse(packet["training_authority"])
        self.assertFalse(packet["release_authority"])
        self.assertFalse(packet["build_authority"])


if __name__ == "__main__":
    unittest.main()
