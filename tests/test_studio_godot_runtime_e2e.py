"""Actual generated Godot replay qualification, source matching and staging.

Tests use real source compilation and isolated mocked native execution. A
separate installed-Godot test runs the real binary whenever available.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.ai.game_builder.studio_asset_pipeline import ArtDirection
from skeleton.ai.game_builder.studio_campaign import CampaignOrder, run_campaign
from skeleton.ai.game_builder.studio_campaign_assurance import (
    StudioAssuranceError, inspect_production_assurance, qualify_campaign_godot,
)
from skeleton.ai.game_builder.studio_godot_qualification import (
    StudioGodotQualificationError, godot_inputs, qualify_godot_headless,
)


class NativeGodotRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        document = self.root / "rights.txt"
        document.write_text("Original owned characters, game mechanics, music, artwork")
        self.order = CampaignOrder(
            project_id="godot-original", title="Original Native Game",
            seed=733, targets=("nintendo_game_boy",),
            source_basis="bandai_wonderswan",
            rights_document=str(document),
            creative_identity=("original-game", "original-art"),
            width=11, height=11, levels=1, collectibles=1,
            hazards=1, health=4, theme="ocean",
            art=ArtDirection(seed=733, animation_frames=3,
                             parallax_layers=0, music_density=0),
        )
        self.campaign = self.root / "campaign"
        result = run_campaign(self.order, self.campaign, authorized=True)
        self.assertEqual(result["targets_with_verified_source"], 1)
        self.engine = self.campaign / "targets/nintendo_game_boy/engines"

    def test_godot_absence_and_preflight_never_count_as_execution(self):
        with patch("skeleton.ai.game_builder.studio_godot_qualification.shutil.which",
                   return_value=None):
            evidence = qualify_godot_headless(self.engine, authorized=True, execute=True)
        self.assertFalse(evidence.godot_available)
        self.assertFalse(evidence.engine_executed)
        self.assertFalse(evidence.game_winning_replay_verified)
        with patch("skeleton.ai.game_builder.studio_godot_qualification.shutil.which",
                   return_value="/usr/bin/godot4"), patch(
                "skeleton.ai.game_builder.studio_godot_qualification.subprocess.run"
            ) as run:
            evidence = qualify_godot_headless(self.engine, authorized=True, execute=False)
        run.assert_not_called()
        self.assertFalse(evidence.engine_executed)
        self.assertEqual(evidence.failure, "native_engine_execution_not_authorized")
        with self.assertRaises(PermissionError):
            qualify_godot_headless(self.engine, authorized=False, execute=True)
        with self.assertRaises(StudioGodotQualificationError):
            qualify_godot_headless(self.engine, authorized=True, execute=True,
                                   timeout_seconds=0)

    def test_headless_execution_receipt_binds_exact_world_and_replay(self):
        source, world, count, source_identity = godot_inputs(self.engine)
        self.assertIn("studio_art.json", source)
        success_line = "NATIVE_REPLAY_OK " + world + " actions=" + str(count) + "\n"
        def fake_run(args, *, cwd, shell, check, timeout, stdout, stderr, env):
            self.assertFalse(shell)
            self.assertFalse(check)
            self.assertTrue(Path(cwd).is_dir())
            self.assertIn("--headless", args)
            self.assertEqual(args[-1], "--verify-proof")
            self.assertEqual(timeout, 45)
            self.assertTrue((Path(args[args.index("--path") + 1]) / "world.json").is_file())
            return subprocess.CompletedProcess(args, 0, success_line.encode(), b"")
        with patch("skeleton.ai.game_builder.studio_godot_qualification.shutil.which",
                   return_value="/opt/godot4"), patch(
            "skeleton.ai.game_builder.studio_godot_qualification.subprocess.run",
            side_effect=fake_run,
        ):
            result = qualify_campaign_godot(
                self.order, self.campaign, "nintendo_game_boy",
                authorized=True, execute=True,
            )
        self.assertTrue(result["godot_headless_gameplay_executed"])
        report = inspect_production_assurance(self.order, self.campaign)
        self.assertEqual(report["godot_headless_playthroughs_verified"], 1)
        self.assertEqual(report["checked_gates"], 8)
        self.assertEqual(
            report["targets"][0]["gates"]["godot_headless_playthrough_executed"]["status"],
            "godot_gameplay_executed",
        )
        self.assertFalse(report["all_targets_release_ready"])
        again = qualify_campaign_godot(
            self.order, self.campaign, "nintendo_game_boy",
            authorized=True, execute=True,
        )
        self.assertTrue(again["already_qualified"])
        self.assertFalse((self.engine / ".godot").exists())

    def test_native_headless_execution_rejects_false_success_and_source_mutation(self):
        _, world, count, _ = godot_inputs(self.engine)
        with patch("skeleton.ai.game_builder.studio_godot_qualification.shutil.which",
                   return_value="/opt/godot4"), patch(
            "skeleton.ai.game_builder.studio_godot_qualification.subprocess.run",
            return_value=subprocess.CompletedProcess(
                ["godot4"], 0, ("NATIVE_REPLAY_OK " + world + " actions=0").encode(), b""
            ),
        ):
            result = qualify_godot_headless(
                self.engine, authorized=True, execute=True,
            )
        self.assertFalse(result.game_winning_replay_verified)
        self.assertEqual(result.failure, "godot_world_or_replay_identity_mismatch")
        source = self.engine / "godot/scripts/main.gd"
        source.write_bytes(source.read_bytes() + b"\n# unexpectedly changed source\n")
        with self.assertRaises(StudioGodotQualificationError):
            godot_inputs(self.engine)
        with self.assertRaises((StudioAssuranceError, ValueError)):
            inspect_production_assurance(self.order, self.campaign)

    def test_real_installed_godot_executes_exact_source_if_available(self):
        if not (shutil.which("godot") or shutil.which("godot4")):
            self.skipTest("Godot 4 binary not available in this runtime")
        proof = qualify_godot_headless(
            self.engine, authorized=True, execute=True, timeout_seconds=90,
        )
        self.assertTrue(proof.godot_available)
        self.assertTrue(proof.engine_executed, proof.failure)
        self.assertTrue(proof.game_winning_replay_verified, proof.failure)
        self.assertFalse(proof.as_receipt()["graphical_framebuffer_verified"])


if __name__ == "__main__":
    unittest.main()
