"""Actual GB/GBC emulator adapter: finite full ROM/controller proof or fail closed.

Synthetic CPU fixtures test exact gates; they do not certify a real PyBoy
playthrough. The optional installed-emulator test uses the actual native ROM.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from skeleton.ai.game_builder.studio_build_qualification import (
    parse_game_boy_symbols,
)
from skeleton.ai.game_builder.studio_game_boy_emulator import (
    GameBoyEmulationError, _receipt, qualify_game_boy_emulator,
)


GB_SYMBOLS = (
    "00:c000 Level\\n00:c001 PlayerX\\n00:c002 PlayerY\\n"
    "00:c006 Health\\n00:c007 Score\\n00:c008 GemsRemaining\\n"
    "00:c009 GameWon\\n00:c00a GameLost\\n00:c00b ScoreHigh\\n00:c00c TurnCount\\n00:c00d TurnCountHigh\\n"
).replace(chr(92) + "n", chr(10)).encode("ascii")


def valid_rom():
    data = bytearray(32768)
    check = 0
    for byte in data[0x134:0x14D]:
        check = (check - byte - 1) & 255
    data[0x14D] = check
    return bytes(data)


class RealCartridgeReplayAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "qualified.rom").write_bytes(valid_rom())
        (self.root / "qualified.sym").write_bytes(GB_SYMBOLS)
        self.world = "c" * 64
        self.proof = json.dumps({
            "schema": "skeleton.game_builder.solution_trace.v1",
            "world_digest": self.world,
            "actions": ["right"],
            "final_state": {
                "status": "won", "x": 2, "y": 1, "score": 0,
                "health": 4, "level_index": 0,
            },
        }).encode()
        self.source = self.root / "engines"
        self.source.mkdir()

    def run_adapter(self, *, execute=True, timeout_seconds=90, max_frames=1200):
        from skeleton.ai.game_builder.studio_native_replay_telemetry import make_checkpoint
        reference = {
            "world_digest": self.world,
            "proof_sha256": sha256(self.proof).hexdigest(),
            "samples": [make_checkpoint(1, {
                "Level": 1, "PlayerX": 2, "PlayerY": 1,
                "Health": 4, "Score": 0, "ScoreHigh": 0,
                "TurnCount": 1, "TurnCountHigh": 0,
                "GemsRemaining": 0, "GameWon": 1, "GameLost": 0,
            })],
        }
        with patch(
            "skeleton.ai.game_builder.studio_game_boy_emulator._engine_inputs",
            return_value=(b"html", self.proof, self.world),
        ), patch(
            "skeleton.ai.game_builder.studio_game_boy_emulator.reference_cpu_checkpoints",
            return_value=reference,
        ):
            return qualify_game_boy_emulator(
                self.root, engine_source=self.source,
                target="nintendo_game_boy", authorized=True, execute=execute,
                timeout_seconds=timeout_seconds, max_frames=max_frames,
            )

    def test_optional_emulator_absent_is_not_called_or_marked_qualified(self):
        with patch("skeleton.ai.game_builder.studio_game_boy_emulator.importlib.util.find_spec",
                   return_value=None):
            result = self.run_adapter()
        self.assertFalse(result.emulator_available)
        self.assertFalse(result.emulator_executed)
        self.assertFalse(result.machine_code_victory)
        self.assertEqual(result.blocker, "pyboy_not_installed")
        self.assertFalse(result.as_receipt()["physical_controller_verified"])

    def test_execution_authority_and_budgets_are_real(self):
        with patch("skeleton.ai.game_builder.studio_game_boy_emulator.importlib.util.find_spec",
                   return_value=object()):
            result = self.run_adapter(execute=False)
        self.assertTrue(result.emulator_available)
        self.assertFalse(result.emulator_executed)
        with self.assertRaises(PermissionError):
            qualify_game_boy_emulator(
                self.root, engine_source=self.source,
                target="nintendo_game_boy", authorized=False, execute=True,
            )
        with self.assertRaises(GameBoyEmulationError):
            self.run_adapter(max_frames=0)

    def test_mocked_machine_state_success_does_not_claim_physical_hardware(self):
        addr = parse_game_boy_symbols(GB_SYMBOLS)
        class FakeLCD:
            ndarray = SimpleNamespace(tobytes=lambda: b"emulated LCD pixel bytes")
        class FakePyBoy:
            def __init__(self, rom, window, sound_emulated):
                self.rom = rom
                self.screen = FakeLCD()
                self.buttons = []
                self.memory = {v: 0 for v in addr.values()}
                self.memory[addr["PlayerX"]] = 1
                self.memory[addr["PlayerY"]] = 1
                self.memory[addr["Health"]] = 4
                self.memory[addr["GemsRemaining"]] = 1
                self.frame = 0
                self.pressed = None
                self.changed = False
                self.stopped = False
            def set_emulation_speed(self, value):
                if value != 0:
                    raise AssertionError("frame limiting should be disabled for verified replay")
            def tick(self):
                self.frame += 1
                if self.pressed == "right" and not self.changed:
                    self.memory[addr["PlayerX"]] = 2
                    self.memory[addr["GemsRemaining"]] = 0
                    self.memory[addr["Level"]] = 1
                    self.memory[addr["TurnCount"]] = 1
                    self.memory[addr["GameWon"]] = 1
                    self.changed = True
            def button_press(self, name):
                self.pressed = name
                self.buttons.append(name)
            def button_release(self, name):
                if self.pressed != name:
                    raise AssertionError("released wrong console controller input")
                self.pressed = None
            def stop(self, save):
                self.stopped = True
                if save:
                    raise AssertionError("emulator must never write save data")
        mod = ModuleType("pyboy")
        mod.PyBoy = FakePyBoy
        with patch.dict(sys.modules, {"pyboy": mod}), patch(
            "skeleton.ai.game_builder.studio_game_boy_emulator.importlib.util.find_spec",
            return_value=object(),
        ):
            result = self.run_adapter()
        self.assertTrue(result.emulator_executed)
        self.assertTrue(result.full_controller_replay)
        self.assertTrue(result.machine_code_victory)
        self.assertEqual(result.source_actions, 1)
        self.assertEqual(result.frames_advanced, 102)
        self.assertEqual(result.last_state["PlayerX"], 2)
        self.assertEqual(result.framebuffer_sha256,
                         sha256(b"emulated LCD pixel bytes").hexdigest())
        receipt = result.as_receipt()
        self.assertFalse(receipt["physical_controller_verified"])
        self.assertFalse(receipt["physical_console_verified"])
        self.assertFalse(receipt["model_training_performed"])

    def test_forged_symbol_map_and_changed_rom_fail_before_emulation(self):
        (self.root / "qualified.sym").write_bytes(b"00:c009 GameWon\\n")
        with self.assertRaises(GameBoyEmulationError):
            self.run_adapter()
        (self.root / "qualified.sym").write_bytes(GB_SYMBOLS)
        (self.root / "qualified.rom").write_bytes(b"not a working ROM")
        with self.assertRaises(GameBoyEmulationError):
            self.run_adapter()

    def test_receipt_change_detection_and_nonwinning_mock(self):
        r = _receipt("nintendo_game_boy", "0" * 64, "1" * 64,
                     self.world, "2" * 64, available=True,
                     executed=True, full=True, won=False,
                     blocker="compiled_cartridge_diverged_from_reference_replay")
        self.assertFalse(r.as_receipt()["machine_code_victory"])
        object.__setattr__(r, "machine_code_victory", True)
        with self.assertRaises(GameBoyEmulationError):
            r.as_receipt()


if __name__ == "__main__":
    unittest.main()
