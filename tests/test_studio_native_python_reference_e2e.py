"""Real authored Python game replay is the independent CPU checkpoint oracle.

No emulator success is assumed. This executes genuine signed world generation,
studio original browser source export and Python game transitions, then checks
the expected *native* zero-page/WRAM state for every sampled action.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.ai.game_builder.studio_asset_pipeline import ArtDirection
from skeleton.ai.game_builder.studio_campaign import CampaignOrder, run_campaign
from skeleton.ai.game_builder.studio_native_replay_telemetry import (
    NativeCheckpointError, reference_cpu_checkpoints, validate_checkpoints,
)
from skeleton.ai.game_builder.studio_runtime_qualification import _inputs


class FullGameCPUMachineReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        rights = root / "original-rights.txt"
        rights.write_text("All art, source, music and game designs are independently authored")
        self.order = CampaignOrder(
            project_id="original-reference-cpu", title="Canonical Machine State",
            seed=733, targets=("nintendo_game_boy",),
            source_basis="bandai_wonderswan",
            rights_document=str(rights),
            creative_identity=("original-maze", "original-sprites"),
            width=11, height=11, levels=3, collectibles=2,
            hazards=0, health=4, theme="forest",
            art=ArtDirection(seed=733, music_density=0, parallax_layers=0),
        )
        self.campaign = root / "campaign"
        status = run_campaign(self.order, self.campaign, authorized=True)
        self.assertEqual(status["targets_with_verified_source"], 1)
        self.engine = self.campaign / "targets/nintendo_game_boy/engines"

    def test_exact_signed_python_moves_generate_native_full_game_checkpoints(self):
        html, proof, world = _inputs(self.engine)
        self.assertIn(b"const GAME =", html)
        original = json.loads(proof)
        reference = reference_cpu_checkpoints(self.engine)
        self.assertEqual(reference["world_digest"], world)
        self.assertEqual(reference["proof_sha256"], sha256(proof).hexdigest())
        self.assertEqual(reference["action_count"], len(original["actions"]))
        self.assertEqual(reference["samples"][-1]["state"]["GameWon"], 1)
        last = reference["samples"][-1]["state"]
        final = original["final_state"]
        self.assertEqual(last["Level"], final["level_index"] + 1)
        self.assertEqual(last["Score"] + last["ScoreHigh"] * 256, final["score"])
        self.assertGreater(final["score"], 255)
        self.assertEqual(last["GemsRemaining"], 0)
        receipt = validate_checkpoints(
            reference["samples"], actions=reference["action_count"],
            source_world=world, source_proof=reference["proof_sha256"],
            expected_final=final, expected_samples=reference["samples"],
        )
        self.assertEqual(receipt["sampled_boundaries"], len(reference["samples"]))
        self.assertFalse(receipt["physical_controller_verified"])

    def test_incorrect_midway_player_position_is_not_mistaken_for_real_cpu_parity(self):
        _, proof, world = _inputs(self.engine)
        reference = reference_cpu_checkpoints(self.engine)
        rows = [{"action": row["action"], "state": dict(row["state"])}
                for row in reference["samples"]]
        self.assertGreaterEqual(len(rows), 3)
        index = len(rows) // 2
        rows[index]["state"]["PlayerX"] ^= 1
        with self.assertRaises(NativeCheckpointError):
            validate_checkpoints(
                rows, actions=reference["action_count"],
                source_world=world, source_proof=sha256(proof).hexdigest(),
                expected_final=json.loads(proof)["final_state"],
                expected_samples=reference["samples"],
            )

    def test_corrupt_regenerated_game_source_is_rejected_before_native_execution(self):
        original = reference_cpu_checkpoints(self.engine)
        with patch(
            "skeleton.ai.game_builder.studio_native_replay_telemetry._game_json",
            return_value={
                "schema": "skeleton.game_builder.browser_game.v1",
                "world_digest": original["world_digest"],
                "intent": {"project_id": "foreign-project"},
                "levels": [],
            },
        ):
            with self.assertRaises(NativeCheckpointError):
                reference_cpu_checkpoints(self.engine)


if __name__ == "__main__":
    unittest.main()
