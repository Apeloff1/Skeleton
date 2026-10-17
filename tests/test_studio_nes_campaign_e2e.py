"""End-to-end NES ROM, linker labels, FCEUX evidence and Dragon gates.

The successful FCEUX response is a synthetic tool boundary in this suite; a
real CPU/PPU playthrough requires the installed emulator and compiler.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.ai.game_builder.studio_asset_pipeline import ArtDirection
from skeleton.ai.game_builder.studio_build_qualification import (
    _receipt as native_receipt, _verify_source,
)
from skeleton.ai.game_builder.studio_campaign import CampaignOrder, run_campaign
from skeleton.ai.game_builder.studio_campaign_assurance import (
    StudioAssuranceError, inspect_production_assurance,
    qualify_campaign_target, qualify_campaign_emulator,
)
from skeleton.ai.game_builder.studio_nes_emulator import _receipt as nes_receipt
from skeleton.ai.game_builder.studio_runtime_qualification import _inputs
from skeleton.ai.game_builder.studio_e2e_observation import observe_production_campaign


NES_LABELS = (
    "al 000000 .Level\n"
    "al 000001 .PlayerX\n"
    "al 000002 .PlayerY\n"
    "al 000005 .Health\n"
    "al 000006 .Score\n"
    "al 000007 .GemsRemaining\n"
    "al 000008 .GameWon\n"
    "al 000009 .GameLost\n"
    "al 000015 .ScoreHigh\n"
    "al 000016 .TurnCount\n"
    "al 000017 .TurnCountHigh\n"
).encode("ascii")


def ines_rom(tiles: bytes, animation: bytes):
    assert len(tiles) == 96
    assert len(animation) == 48 and animation[:16] == tiles[80:96]
    char = tiles + animation[16:]
    return (
        b"NES\x1a" + bytes([1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
        + bytes(16384) + char + bytes(8192 - len(char))
    )

class OriginalNESCampaignGatesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        rights = self.root / "ownership.txt"
        rights.write_text("Original characters, music, artworks, and mechanics")
        self.order = CampaignOrder(
            project_id="nesoriginal", title="NROM Real CPU Verification",
            seed=733, targets=("nintendo_famicom",),
            source_basis="bandai_wonderswan", rights_document=str(rights),
            creative_identity=("original-homebrew", "owned-art"),
            width=11, height=11, levels=1, collectibles=1,
            hazards=1, health=4, theme="forest",
            art=ArtDirection(seed=733, music_density=0, parallax_layers=0),
        )
        self.campaign = self.root / "campaign"
        run_campaign(self.order, self.campaign, authorized=True)

    def compile_fixture(self):
        original = (self.campaign / "targets/nintendo_famicom/assets/tiles/runtime.bin").read_bytes()
        rom = ines_rom(
            original,
            (self.campaign / "targets/nintendo_famicom/assets/tiles/hero_animation.bin").read_bytes(),
        )
        def assembler(project, target, *, authorized, execute, output,
                      output_symbols, timeout_seconds):
            self.assertEqual(target, "nintendo_famicom")
            Path(output).write_bytes(rom)
            Path(output_symbols).write_bytes(NES_LABELS)
            _, digest = _verify_source(Path(project), target)
            return native_receipt(
                target, digest, available=True, invoked=True,
                built=True, header=True, digest=sha256(rom).hexdigest(),
                size=len(rom), symbol_sha256=sha256(NES_LABELS).hexdigest(),
            )
        with patch(
            "skeleton.ai.game_builder.studio_campaign_assurance.qualify_native_build",
            side_effect=assembler,
        ):
            result = qualify_campaign_target(
                self.order, self.campaign, "nintendo_famicom",
                authorized=True, execute=True,
            )
        self.assertTrue(result["native_rom_compiled"])
        return rom

    def test_verified_cpu_and_ppu_replay_binds_rom_symbols_source_and_observation(self):
        rom = self.compile_fixture()
        html, proof, world = _inputs(
            self.campaign / "targets/nintendo_famicom/engines",
        )
        del html
        trace = json.loads(proof)
        final = trace["final_state"]
        ram = {
            "Level": final["level_index"] + 1,
            "PlayerX": final["x"], "PlayerY": final["y"],
            "Health": final["health"], "Score": final["score"] % 256,
            "ScoreHigh": final["score"] // 256,
            "TurnCount": len(trace["actions"]) & 255,
            "TurnCountHigh": len(trace["actions"]) >> 8,
            "GemsRemaining": 0, "GameWon": 1, "GameLost": 0,
        }
        fake = nes_receipt(
            sha256(rom).hexdigest(), sha256(NES_LABELS).hexdigest(),
            world, sha256(proof).hexdigest(), available=True, executed=True,
            replay=True, victory=True, frames=1500,
            actions=len(trace["actions"]),
            image="a" * 64, checkpoint="d" * 64, sampled=1, state=ram,
        )
        with patch(
            "skeleton.ai.game_builder.studio_campaign_assurance.qualify_nes_cpu_ppu",
            return_value=fake,
        ) as native:
            passed = qualify_campaign_emulator(
                self.order, self.campaign, "nintendo_famicom",
                authorized=True, execute=True,
            )
        native.assert_called_once()
        self.assertTrue(passed["machine_code_victory"])
        report = inspect_production_assurance(self.order, self.campaign)
        self.assertEqual(report["native_rom_machine_code_playthroughs_verified"], 1)
        self.assertEqual(
            report["targets"][0]["gates"]["emulator_playthrough_executed"]["status"],
            "machine_code_controller_replay_verified",
        )
        self.assertEqual(
            report["targets"][0]["gates"]["controller_response_verified"]["status"],
            "machine_code_controller_replay_verified",
        )
        observation = observe_production_campaign(
            self.order, self.campaign, authorized=True,
        )
        self.assertEqual(observation["actual_native_rom_victory_replays"], 1)
        self.assertFalse(observation["learned_new_weights"])
        self.assertFalse(report["all_targets_release_ready"])
        (self.campaign / "qualifications/nintendo_famicom/qualified.sym").write_bytes(
            b"wrong linker exported addresses"
        )
        with self.assertRaises(StudioAssuranceError):
            inspect_production_assurance(self.order, self.campaign)

    def test_wrong_compiled_chr_pixels_never_publish_a_qualified_nes(self):
        corrupted = bytearray(ines_rom(
            (self.campaign / "targets/nintendo_famicom/assets/tiles/runtime.bin").read_bytes(),
            (self.campaign / "targets/nintendo_famicom/assets/tiles/hero_animation.bin").read_bytes(),
        ))
        start = 16 + 16384
        corrupted[start] ^= 0xFF

        def assembler(project, target, *, authorized, execute, output,
                      output_symbols, timeout_seconds):
            binary = bytes(corrupted)
            Path(output).write_bytes(binary)
            Path(output_symbols).write_bytes(NES_LABELS)
            _, digest = _verify_source(Path(project), target)
            return native_receipt(
                target, digest, available=True, invoked=True,
                built=True, header=True, digest=sha256(binary).hexdigest(),
                size=len(binary), symbol_sha256=sha256(NES_LABELS).hexdigest(),
            )
        with patch(
            "skeleton.ai.game_builder.studio_campaign_assurance.qualify_native_build",
            side_effect=assembler,
        ):
            status = qualify_campaign_target(
                self.order, self.campaign, "nintendo_famicom",
                authorized=True, execute=True,
            )
        self.assertFalse(status["native_rom_compiled"])
        self.assertEqual(status["blocker"], "compiled_nes_chr_original_art_mismatch")
        self.assertFalse(
            (self.campaign / "qualifications/nintendo_famicom/qualified.rom").exists()
        )
        self.assertFalse(
            (self.campaign / "qualifications/nintendo_famicom/qualified.sym").exists()
        )

    def test_missing_emulator_or_cpu_win_cannot_publish_positive_gate(self):
        self.compile_fixture()
        html, proof, world = _inputs(
            self.campaign / "targets/nintendo_famicom/engines",
        )
        del html
        failure = nes_receipt(
            sha256(ines_rom(
                (self.campaign / "targets/nintendo_famicom/assets/tiles/runtime.bin").read_bytes(),
                (self.campaign / "targets/nintendo_famicom/assets/tiles/hero_animation.bin").read_bytes(),
            )).hexdigest(), sha256(NES_LABELS).hexdigest(),
            world, sha256(proof).hexdigest(), available=False,
            blocker="fceux_not_installed",
        )
        with patch(
            "skeleton.ai.game_builder.studio_campaign_assurance.qualify_nes_cpu_ppu",
            return_value=failure,
        ):
            result = qualify_campaign_emulator(
                self.order, self.campaign, "nintendo_famicom",
                authorized=True, execute=True,
            )
        self.assertFalse(result["machine_code_victory"])
        self.assertEqual(result["blocker"], "fceux_not_installed")
        self.assertEqual(
            inspect_production_assurance(
                self.order, self.campaign
            )["native_rom_machine_code_playthroughs_verified"], 0
        )


if __name__ == "__main__":
    unittest.main()
