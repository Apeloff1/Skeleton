"""Native NROM/6502 FCEUX evidence and exact zero-page controller replay."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from skeleton.ai.game_builder.studio_build_qualification import parse_nes_labels
from skeleton.ai.game_builder.studio_nes_emulator import (
    NativeNESEmulationError, _receipt, _script, qualify_nes_cpu_ppu,
)


NES_LABELS = (
    "al 000000 .Level\n"
    "al 000001 .PlayerX\n"
    "al 000002 .PlayerY\n"
    "al 000005 .Health\n"
    "al 000006 .Score\n"
    "al 000007 .GemsRemaining\n"
    "al 000008 .GameWon\n"
    "al 000009 .GameLost\n"\n    "al 000015 .ScoreHigh\n"
).encode("ascii")


def cartridge() -> bytes:
    return b"NES\x1a" + bytes([1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]) + bytes(16384 + 8192)


class RealNESCPUReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = self.root / "engines"
        self.engine.mkdir()
        (self.root / "qualified.rom").write_bytes(cartridge())
        (self.root / "qualified.sym").write_bytes(NES_LABELS)
        self.world = "a" * 64
        self.proof = json.dumps({
            "schema": "skeleton.game_builder.solution_trace.v1",
            "world_digest": self.world,
            "actions": ["right", "up"],
            "final_state": {"status": "won", "x": 2, "y": 3,
                            "health": 4, "score": 1, "level_index": 0},
        }).encode("utf-8")

    def execute(self, *, authorized=True, execute=True, max_frames=1500):
        with patch(
            "skeleton.ai.game_builder.studio_nes_emulator._inputs",
            return_value=(b"original html", self.proof, self.world),
        ):
            return qualify_nes_cpu_ppu(
                self.root, engine_source=self.engine,
                authorized=authorized, execute=execute,
                max_frames=max_frames,
            )

    def test_real_ld65_zero_page_labels_and_fixed_original_lua(self):
        addresses = parse_nes_labels(NES_LABELS)
        self.assertEqual(addresses["GameWon"], 8)
        self.assertEqual(addresses["Score"], 6)
        script = _script(["right", "up"], addresses, max_frames=1500)
        self.assertIn('local actions = {"right","up"}', script)
        self.assertIn("memory.readbyte(ram.GameWon)", script)
        self.assertIn("joypad.set(1, {[button]=true})", script)
        self.assertIn("gui.gdscreenshot(true)", script)
        self.assertNotIn("memory.writebyte", script)

    def test_uninstalled_fceux_and_denied_execution_not_claimed_victorious(self):
        with patch("skeleton.ai.game_builder.studio_nes_emulator.shutil.which",
                   return_value=None):
            result = self.execute()
        self.assertFalse(result.emulator_available)
        self.assertFalse(result.machine_code_victory)
        self.assertEqual(result.blocker, "fceux_not_installed")
        with patch("skeleton.ai.game_builder.studio_nes_emulator.shutil.which",
                   return_value="/opt/fceux"), patch(
            "skeleton.ai.game_builder.studio_nes_emulator.subprocess.run"
        ) as runner:
            preview = self.execute(execute=False)
        runner.assert_not_called()
        self.assertFalse(preview.emulator_executed)
        with self.assertRaises(PermissionError):
            self.execute(authorized=False)
        with self.assertRaises(NativeNESEmulationError):
            self.execute(max_frames=0)

    def test_mocked_native_6502_response_is_still_not_real_runtime_certificate(self):
        def simulated_fceux(args, *, cwd, shell, check, timeout,
                            stdout, stderr, env):
            self.assertFalse(shell)
            self.assertFalse(check)
            self.assertIn("--loadlua", args)
            self.assertEqual(timeout, 90)
            script = Path(args[args.index("--loadlua") + 1]).read_text()
            self.assertIn('{"right","up"}', script)
            self.assertTrue((Path(cwd) / "original.nes").exists())
            self.assertFalse((Path(cwd) / "original.nes").is_symlink())
            (Path(cwd) / "replay-result.txt").write_text(
                "NES_REPLAY_V1 150 2 1 2 3 4 1 0 0 1 0"
            )
            (Path(cwd) / "framebuffer.gd").write_bytes(b"GDREAL" + bytes(300))
            (Path(cwd) / "cpu-snapshots.txt").write_text(
                "1 0 2 4 4 0 0 1 0 0\\n"
                "2 1 2 3 4 1 0 0 1 0\\n".replace("\\\\n", "\\n")
            )
            return subprocess.CompletedProcess(args, 0, None, None)
        with patch("skeleton.ai.game_builder.studio_nes_emulator.shutil.which",
                   return_value="/opt/fceux"), patch(
            "skeleton.ai.game_builder.studio_nes_emulator.subprocess.run",
            side_effect=simulated_fceux,
        ) as executor:
            result = self.execute()
        executor.assert_called_once()
        self.assertTrue(result.machine_code_victory)
        self.assertTrue(result.cpu_input_replay_executed)
        self.assertEqual(result.frame_count, 150)
        self.assertEqual(result.action_count, 2)
        self.assertEqual(result.ppu_frame_sha256,
                         sha256(b"GDREAL" + bytes(300)).hexdigest())
        evidence = result.as_receipt()
        self.assertFalse(evidence["physical_controller_verified"])
        self.assertFalse(evidence["model_weights_changed"])
        self.assertFalse(evidence["release_approved"])

    def test_a_lost_or_stale_game_can_never_pass_native_replay(self):
        with patch("skeleton.ai.game_builder.studio_nes_emulator.shutil.which",
                   return_value="/opt/fceux"), patch(
            "skeleton.ai.game_builder.studio_nes_emulator.subprocess.run",
            side_effect=lambda args, *, cwd, **k: (
                (Path(cwd) / "replay-result.txt").write_text(
                    "NES_REPLAY_V1 150 2 1 2 3 0 1 0 0 0 1"
                ) and subprocess.CompletedProcess(args, 0, None, None)
            ),
        ):
            result = self.execute()
        self.assertFalse(result.machine_code_victory)
        self.assertEqual(result.blocker, "nes_machine_code_diverged_from_reference_replay")
        (self.root / "qualified.sym").write_text("falsified linker state")
        with self.assertRaises(NativeNESEmulationError):
            self.execute()

    def test_runtime_does_not_trust_tampered_emulation_receipts(self):
        r = _receipt(
            "0" * 64, "1" * 64, self.world, "2" * 64,
            available=True, executed=True, replay=True, victory=False,
            blocker="nes_machine_code_diverged_from_reference_replay",
        )
        self.assertFalse(r.as_receipt()["machine_code_victory"])
        object.__setattr__(r, "machine_code_victory", True)
        with self.assertRaises(NativeNESEmulationError):
            r.as_receipt()


if __name__ == "__main__":
    unittest.main()
