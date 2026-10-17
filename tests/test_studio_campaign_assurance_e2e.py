"""E2E assurance: source provenance, actual ROM structure and blocked releases.

The assembler is mocked only in the successful ROM test; that test proves
binding and structural gating, not real toolchain correctness or gameplay.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from skeleton.ai.game_builder.studio_asset_pipeline import ArtDirection
from skeleton.ai.game_builder.studio_build_qualification import (
    _receipt, _verify_source,
)
from skeleton.ai.game_builder.studio_campaign import CampaignOrder, run_campaign
from skeleton.ai.game_builder.studio_campaign_lock import StudioCampaignBusy, campaign_lock
from skeleton.ai.game_builder.studio_campaign_assurance import (
    StudioAssuranceError, GATES, inspect_production_assurance, qualify_campaign_target,
)
from skeleton.ai.game_builder.studio_e2e_observation import (
    observe_production_campaign,
)


def sample_rom() -> bytes:
    data = bytearray(32768)
    checksum = 0
    for item in data[0x134:0x14D]:
        checksum = (checksum - item - 1) & 255
    data[0x14D] = checksum
    return bytes(data)


GB_SYMBOLS = (
    "00:c000 Level\\n00:c001 PlayerX\\n00:c002 PlayerY\\n"
    "00:c006 Health\\n00:c007 Score\\n00:c008 GemsRemaining\\n"
    "00:c009 GameWon\\n00:c00a GameLost\\n"
).replace(chr(92) + "n", chr(10)).encode("ascii")


class ProductionGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        evidence = self.base / "ownership.txt"
        evidence.write_text("This is an independently authored original game.")
        self.order = CampaignOrder(
            project_id="auditstudio", title="Original Dragon Adventure",
            seed=733, targets=("nintendo_game_boy", "nintendo_famicom"),
            source_basis="bandai_wonderswan",
            rights_document=str(evidence),
            creative_identity=("original-game", "original-art"),
            width=11, height=11, levels=1, collectibles=1,
            hazards=1, health=4, theme="ocean",
            art=ArtDirection(seed=733, animation_frames=2,
                             music_density=0, parallax_layers=0),
        )
        self.root = self.base / "campaign"

    def test_incomplete_and_complete_source_are_not_release_ready(self):
        run_campaign(self.order, self.root, authorized=True, max_targets=1)
        report = inspect_production_assurance(self.order, self.root)
        self.assertEqual(len(GATES), 20)
        self.assertEqual(report["total_targets"], 2)
        self.assertEqual(report["targets_with_exact_source"], 1)
        self.assertEqual(report["checked_gates"], 8)
        self.assertFalse(report["all_targets_release_ready"])
        self.assertEqual(report["release_qualification_percent"], 0)
        self.assertFalse(report["rights_approval_inferred"])
        self.assertFalse(report["dragon_training_or_weight_promotion_performed"])
        self.assertEqual(
            report["targets"][0]["gates"]["indexed_sprites_and_descriptors"]["status"],
            "artifact_integrity_checked",
        )
        self.assertEqual(
            report["targets"][0]["gates"]["emulator_playthrough_executed"]["status"],
            "not_qualified",
        )
        self.assertEqual(
            report["targets"][1]["gates"]["original_world_source"]["status"],
            "not_qualified",
        )
        run_campaign(self.order, self.root, authorized=True)
        report = inspect_production_assurance(self.order, self.root)
        self.assertEqual(report["targets_with_exact_source"], 2)
        self.assertEqual(report["checked_gates"], 16)
        self.assertEqual(report["native_roms_structurally_verified"], 0)
        self.assertFalse(report["all_targets_release_ready"])

    def test_structural_rom_qualification_requires_real_bound_source(self):
        run_campaign(self.order, self.root, authorized=True, max_targets=1)
        rom = sample_rom()

        def simulated_compiler(project, target, *, authorized, execute,
                               output, output_symbols, timeout_seconds):
            self.assertEqual(target, "nintendo_game_boy")
            self.assertTrue(authorized)
            self.assertTrue(execute)
            self.assertEqual(timeout_seconds, 45)
            Path(output).write_bytes(rom)
            Path(output_symbols).write_bytes(GB_SYMBOLS)
            _, source = _verify_source(Path(project), target)
            return _receipt(target, source, available=True, invoked=True,
                            built=True, header=True,
                            digest=sha256(rom).hexdigest(), size=len(rom),
                            symbol_sha256=sha256(GB_SYMBOLS).hexdigest())

        with patch(
            "skeleton.ai.game_builder.studio_campaign_assurance.qualify_native_build",
            side_effect=simulated_compiler,
        ) as execute:
            build = qualify_campaign_target(
                self.order, self.root, "nintendo_game_boy",
                authorized=True, execute=True,
            )
        execute.assert_called_once()
        self.assertTrue(build["native_rom_compiled"])
        self.assertFalse(build["already_qualified"])
        report = inspect_production_assurance(self.order, self.root)
        self.assertEqual(report["native_roms_structurally_verified"], 1)
        self.assertEqual(report["checked_gates"], 10)
        self.assertEqual(
            report["targets"][0]["gates"]["cartridge_structure_checked"]["status"],
            "binary_structure_checked",
        )
        self.assertEqual(
            report["targets"][0]["gates"]["controller_response_verified"]["status"],
            "not_qualified",
        )
        replay = qualify_campaign_target(
            self.order, self.root, "nintendo_game_boy", authorized=True, execute=True,
        )
        self.assertTrue(replay["already_qualified"])
        self.assertEqual(replay["evidence_digest"], build["evidence_digest"])
        observation = observe_production_campaign(
            self.order, self.root, authorized=True,
        )
        self.assertEqual(observation["source_completed_target_count"], 1)
        self.assertEqual(observation["rom_structurally_checked_count"], 1)
        self.assertEqual(observation["total_observations"], 3)
        self.assertEqual(observation["observations"][2]["kind"],
                         "studio.rom_structure_checked")
        self.assertFalse(observation["learned_new_weights"])
        self.assertFalse(observation["release_ready"])
        self.assertFalse(observation["screen_or_video_recorded"])

    def test_negative_controller_rights_and_model_evidence_cannot_be_forged(self):
        run_campaign(self.order, self.root, authorized=True, max_targets=1)
        with self.assertRaises(PermissionError):
            observe_production_campaign(self.order, self.root, authorized=False)
        with self.assertRaises(PermissionError):
            qualify_campaign_target(
                self.order, self.root, "nintendo_game_boy",
                authorized=False, execute=True,
            )
        with self.assertRaises(StudioAssuranceError):
            qualify_campaign_target(
                self.order, self.root, "nintendo_game_boy",
                authorized=True, execute=False,
            )
        with self.assertRaises(StudioAssuranceError):
            qualify_campaign_target(
                self.order, self.root, "nintendo_game_boy_color",
                authorized=True, execute=True,
            )
        with self.assertRaises(StudioAssuranceError):
            qualify_campaign_target(
                self.order, self.root, "nintendo_famicom",
                authorized=True, execute=True,
            )
        with self.assertRaises(ValueError):
            observe_production_campaign(
                self.order, self.root, authorized=True, after=True,
            )
        with self.assertRaises(ValueError):
            observe_production_campaign(
                self.order, self.root, authorized=True, limit=1000,
            )
        with self.assertRaises(ValueError):
            inspect_production_assurance(replace(self.order, seed=734), self.root)

    def test_qualified_rom_tampering_never_survives_gate_inspection(self):
        run_campaign(self.order, self.root, authorized=True, max_targets=1)
        rom = sample_rom()

        def fake_compiler(project, target, *, authorized, execute, output,
                          output_symbols, timeout_seconds):
            Path(output).write_bytes(rom)
            Path(output_symbols).write_bytes(GB_SYMBOLS)
            _, digest = _verify_source(Path(project), target)
            return _receipt(target, digest, available=True, invoked=True,
                            built=True, header=True,
                            digest=sha256(rom).hexdigest(), size=len(rom),
                            symbol_sha256=sha256(GB_SYMBOLS).hexdigest())

        with patch(
            "skeleton.ai.game_builder.studio_campaign_assurance.qualify_native_build",
            side_effect=fake_compiler,
        ):
            qualify_campaign_target(
                self.order, self.root, "nintendo_game_boy",
                authorized=True, execute=True,
            )
        recorded = self.root / "qualifications/nintendo_game_boy/qualified.rom"
        recorded.write_bytes(b"not an original cartridge")
        with self.assertRaises(StudioAssuranceError):
            inspect_production_assurance(self.order, self.root)

    def test_campaign_lock_prevents_concurrent_writers_and_readers(self):
        with campaign_lock(self.root):
            with self.assertRaises(StudioCampaignBusy):
                run_campaign(self.order, self.root, authorized=True)
            with self.assertRaises(StudioCampaignBusy):
                inspect_production_assurance(self.order, self.root)
        self.assertEqual(run_campaign(
            self.order, self.root, authorized=True, max_targets=1,
        )["targets_with_verified_source"], 1)
        self.assertTrue((self.base / ".campaign.campaign.lock").exists())


if __name__ == "__main__":
    unittest.main()
