"""Dragon cannot convert unverified game production into knowledge or weights."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from skeleton.ai.game_builder.studio_asset_pipeline import ArtDirection
from skeleton.ai.game_builder.studio_campaign import CampaignOrder, run_campaign
from skeleton.ai.game_builder.studio_dragon_learning_bridge import (
    DragonOperationalLessonError,
    propose_dragon_operational_lessons,
    review_dragon_operational_lesson,
    inspect_dragon_reviewed_lessons,
)


class SourceBoundDragonOperationalLearningTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = self.root / "ownership.txt"
        source.write_text("An independently created original homebrew studio game")
        self.order = CampaignOrder(
            project_id="dragonlessons", title="Reviewed Learning Game",
            seed=733, targets=("nintendo_game_boy", "nintendo_famicom"),
            source_basis="bandai_wonderswan", rights_document=str(source),
            creative_identity=("homebrew-art", "original-gameplay"),
            width=11, height=11, levels=1, collectibles=1,
            hazards=1, health=4, theme="forest",
            art=ArtDirection(seed=733, music_density=0, parallax_layers=0),
        )
        self.campaign = self.root / "campaign"
        checked = run_campaign(self.order, self.campaign,
                               authorized=True, max_targets=1)
        self.assertEqual(checked["targets_with_verified_source"], 1)

    def test_derive_actionable_lesson_proposals_from_real_missing_gates(self):
        report = propose_dragon_operational_lessons(
            self.order, self.campaign, authorized=True, limit=64,
        )
        self.assertEqual(report["schema"], "skeleton.game_builder.dragon_operational_lessons.v1")
        self.assertGreater(report["candidate_count"], 1)
        self.assertLessEqual(report["candidate_count"], 64)
        self.assertFalse(report["weights_changed"])
        self.assertFalse(report["almanac_knowledge_promoted"])
        self.assertTrue(report["review_required"])
        self.assertTrue(any(x["blocker"] == "source_not_generated"
                            for x in report["candidates"]))
        self.assertTrue(any(x["gate"] == "native_rom_compiled"
                            for x in report["candidates"]))
        self.assertEqual(len({x["candidate_digest"] for x in report["candidates"]}),
                         report["candidate_count"])
        for candidate in report["candidates"]:
            self.assertFalse(candidate["model_weights_modified"])
            self.assertFalse(candidate["knowledge_reviewed"])
            self.assertFalse(candidate["automatic_retry_authorized"])
            self.assertNotIn("prompt", candidate)
            self.assertNotIn("raw_source", candidate)

    def test_human_review_stays_source_bound_and_no_automatic_training(self):
        proposed = propose_dragon_operational_lessons(
            self.order, self.campaign, authorized=True,
        )
        candidate = proposed["candidates"][0]
        note = "Require real platform execution before promoting this result."
        with self.assertRaises(PermissionError):
            review_dragon_operational_lesson(
                self.order, self.campaign, candidate["candidate_digest"],
                "approve_for_reviewed_knowledge", note,
                authorized=True, human_reviewed=False,
            )
        review = review_dragon_operational_lesson(
            self.order, self.campaign, candidate["candidate_digest"],
            "approve_for_reviewed_knowledge", note,
            authorized=True, human_reviewed=True,
        )
        self.assertTrue(review["human_reviewed"])
        self.assertFalse(review["knowledge_promoted"])
        self.assertFalse(review["model_weights_modified"])
        self.assertFalse(review["training_authorized"])
        self.assertEqual(review["candidate_digest"], candidate["candidate_digest"])
        same = review_dragon_operational_lesson(
            self.order, self.campaign, candidate["candidate_digest"],
            "approve_for_reviewed_knowledge", note,
            authorized=True, human_reviewed=True,
        )
        self.assertEqual(same, review)
        summary = inspect_dragon_reviewed_lessons(
            self.order, self.campaign, authorized=True,
        )
        self.assertEqual(summary["human_reviewed_lessons"], 1)
        self.assertEqual(summary["approved_operational_drafts"], 1)
        self.assertFalse(summary["knowledge_promoted"])
        self.assertFalse(summary["model_training_performed"])

    def test_stale_source_requires_new_review_and_changed_reviews_fail(self):
        proposal = propose_dragon_operational_lessons(
            self.order, self.campaign, authorized=True,
        )
        candidate = proposal["candidates"][0]
        review_dragon_operational_lesson(
            self.order, self.campaign, candidate["candidate_digest"],
            "needs_more_evidence",
            "Do not promote a finding until independent emulator execution.",
            authorized=True, human_reviewed=True,
        )
        saved = self.campaign / "dragon_reviews" / (candidate["candidate_digest"] + ".json")
        payload = json.loads(saved.read_text())
        payload["model_weights_modified"] = True
        saved.write_text(json.dumps(payload))
        with self.assertRaises(DragonOperationalLessonError):
            inspect_dragon_reviewed_lessons(
                self.order, self.campaign, authorized=True,
            )

    def test_cannot_reuse_old_candidate_after_actual_new_source_checkpoint(self):
        first = propose_dragon_operational_lessons(
            self.order, self.campaign, authorized=True,
        )["candidates"][0]
        finished = run_campaign(self.order, self.campaign, authorized=True)
        self.assertEqual(finished["targets_with_verified_source"], 2)
        with self.assertRaises(DragonOperationalLessonError):
            review_dragon_operational_lesson(
                self.order, self.campaign, first["candidate_digest"],
                "approve_for_reviewed_knowledge",
                "This old gate was resolved; do not reuse the earlier review.",
                authorized=True, human_reviewed=True,
            )

    def test_review_input_and_permissions_cannot_promote_model_training(self):
        candidate = propose_dragon_operational_lessons(
            self.order, self.campaign, authorized=True,
        )["candidates"][0]
        with self.assertRaises(PermissionError):
            propose_dragon_operational_lessons(
                self.order, self.campaign, authorized=False,
            )
        for decision, note in (("automatically_train", "Approve weights now"),
                               ("approve_for_reviewed_knowledge", "short")):
            with self.subTest(decision=decision, note=note):
                with self.assertRaises(DragonOperationalLessonError):
                    review_dragon_operational_lesson(
                        self.order, self.campaign, candidate["candidate_digest"],
                        decision, note, authorized=True, human_reviewed=True,
                    )
        with self.assertRaises(DragonOperationalLessonError):
            review_dragon_operational_lesson(
                self.order, self.campaign, "not-a-source-digest",
                "approve_for_reviewed_knowledge",
                "Actual independent evidence must be collected.",
                authorized=True, human_reviewed=True,
            )


if __name__ == "__main__":
    unittest.main()
