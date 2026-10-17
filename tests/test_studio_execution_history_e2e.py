"""Long-running studio production needs durable, nonfictitious E2E receipts."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from skeleton.ai.game_builder.contracts import canonical_digest
from skeleton.ai.game_builder.studio_native_correction_triage import triage_native_gameplay
from skeleton.ai.game_builder.studio_asset_pipeline import ArtDirection
from skeleton.ai.game_builder.studio_campaign import CampaignOrder
from skeleton.ai.game_builder.studio_execution_campaign import (
    ExecutionPolicy, run_studio_execution_campaign,
)
from skeleton.ai.game_builder.studio_execution_history import (
    StudioQualificationHistoryError, record_execution_run,
    inspect_execution_history,
)


class EnduranceProductionHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        rights = self.root / "authorship.txt"
        rights.write_text("All original tiles, levels and game assets authored here")
        self.order = CampaignOrder(
            project_id="enduranceoriginal", title="Durable Production State",
            seed=733, targets=("nintendo_game_boy", "nintendo_famicom"),
            source_basis="bandai_wonderswan", rights_document=str(rights),
            creative_identity=("original-art", "original-game"),
            width=11, height=11, levels=1, collectibles=1, hazards=1,
            health=4, theme="forest",
            art=ArtDirection(seed=733, music_density=0, parallax_layers=0),
        )
        self.campaign = self.root / "campaign"

    def source_attempt(self, limit=1):
        return run_studio_execution_campaign(
            self.order, self.campaign,
            policy=ExecutionPolicy(stages=("source",),
                                   max_sources_per_run=limit),
            authorized=True, execute=True,
        )

    def test_journal_survives_resume_without_duplicating_unverified_releases(self):
        one = self.source_attempt()
        first = record_execution_run(
            self.order, self.campaign, one, authorized=True,
        )
        self.assertEqual(first["sequence"], 1)
        state = inspect_execution_history(
            self.order, self.campaign, authorized=True,
        )
        self.assertEqual(state["recorded_runs"], 1)
        self.assertTrue(state["latest_still_matches_current_source"])
        self.assertFalse(state["complete_game_release_certified"])
        self.assertFalse(state["model_training_performed"])
        two = self.source_attempt()
        self.assertEqual(two["verified_stage_attempts"], 2)
        state = inspect_execution_history(
            self.order, self.campaign, authorized=True,
        )
        self.assertFalse(state["latest_still_matches_current_source"])
        with self.assertRaises(StudioQualificationHistoryError):
            record_execution_run(
                self.order, self.campaign, one, authorized=True,
            )
        second = record_execution_run(
            self.order, self.campaign, two, authorized=True,
        )
        self.assertEqual(second["sequence"], 2)
        self.assertEqual(second["previous_entry_digest"], first["entry_digest"])
        latest = inspect_execution_history(
            self.order, self.campaign, authorized=True,
        )
        self.assertEqual(latest["recorded_runs"], 2)
        self.assertTrue(latest["latest_still_matches_current_source"])
        self.assertEqual(latest["runs_without_recorded_blockers"], 1)

    def test_operator_history_keeps_first_bounded_native_cpu_failure_diagnostic(self):
        # This is an explicitly synthetic failed emulator boundary, not a
        # claimed execution of PyBoy or FCEUX on a compiled cartridge.
        mismatch = {
            "category": "cpu_state_diverged", "first_sample_index": 0,
            "action": 1, "changed_fields": ["PlayerX"],
            "expected": {"PlayerX": 2}, "observed": {"PlayerX": 3},
        }
        with patch(
            "skeleton.ai.game_builder.studio_execution_campaign.qualify_campaign_emulator",
            return_value={
                "machine_code_victory": False,
                "blocker": "native_cpu_checkpoint_state_mismatch",
                "first_cpu_divergence": mismatch,
            },
        ):
            run = run_studio_execution_campaign(
                self.order, self.campaign,
                policy=ExecutionPolicy(stages=("source", "emulator")),
                authorized=True, execute=True,
            )
        self.assertEqual(run["blocked_stage_attempts"], 2)
        recorded = record_execution_run(
            self.order, self.campaign, run, authorized=True,
        )
        self.assertEqual(recorded["native_cpu_divergence_count"], 2)
        self.assertEqual(recorded["first_native_cpu_divergence"]["first_action"], 1)
        self.assertEqual(recorded["first_native_cpu_divergence"]["changed_fields"], ["PlayerX"])
        self.assertEqual(
            inspect_execution_history(self.order, self.campaign, authorized=True)
            ["recorded_cpu_divergence_events"], 2,
        )
        dragon = triage_native_gameplay(
            self.order, self.campaign, authorized=True,
        )
        self.assertTrue(dragon["latest_history_current"])
        self.assertEqual(dragon["proposal_count"], 1)
        self.assertEqual(dragon["proposals"][0]["first_mismatch_action"], 1)
        self.assertEqual(dragon["proposals"][0]["category"],
                         "directional_input_or_collision")
        self.assertFalse(dragon["source_code_modified"])
        self.assertFalse(dragon["model_weights_modified"])
        forged = dict(run)
        forged["events"] = [*run["events"], dict(run["events"][-1])]
        forged["total_stage_attempts"] += 1
        forged["blocked_stage_attempts"] += 1
        forged["run_digest"] = canonical_digest({
            key: value for key, value in forged.items() if key != "run_digest"
        })
        with self.assertRaises(StudioQualificationHistoryError):
            record_execution_run(
                self.order, self.campaign, forged, authorized=True,
            )

    def test_hash_chain_rejects_modified_events_and_unauthorized_appends(self):
        attempt = self.source_attempt(limit=2)
        record_execution_run(
            self.order, self.campaign, attempt, authorized=True,
        )
        with self.assertRaises(PermissionError):
            record_execution_run(self.order, self.campaign, attempt, authorized=False)
        path = self.campaign / "qualification_history.json"
        content = json.loads(path.read_text())
        content["entries"][0]["blocked_stage_attempts"] = 0
        path.write_text(json.dumps(content))
        with self.assertRaises(StudioQualificationHistoryError):
            inspect_execution_history(
                self.order, self.campaign, authorized=True,
            )

    def test_repeatable_same_source_does_not_mean_full_game_release(self):
        first = self.source_attempt(limit=2)
        record_execution_run(
            self.order, self.campaign, first, authorized=True,
        )
        second = self.source_attempt(limit=2)
        last = record_execution_run(
            self.order, self.campaign, second, authorized=True,
        )
        self.assertEqual(last["sequence"], 2)
        state = inspect_execution_history(
            self.order, self.campaign, authorized=True,
        )
        self.assertEqual(state["recorded_runs"], 2)
        self.assertFalse(state["complete_game_release_certified"])
        self.assertEqual(state["runs_without_recorded_blockers"], 2)


if __name__ == "__main__":
    unittest.main()
