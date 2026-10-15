"""Synthetic source-level first-boot audit tests (no installed emulator/BIOS/ROM)."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.audit_game_emulator_first_boot import (
    SCHEMA, FirstBootError, _manifest, _run_case, run_matrix,
)


def checksum(value):
    return hashlib.sha256(value).hexdigest()


def signature(value):
    return checksum(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


class StubNativeHost:
    """Stateful source stand-in: explicitly NOT a native libretro core."""

    def __init__(self, *, diverge=False):
        self.core = type("StubCore", (), {"library_sha256": "a" * 64})()
        self.spec = type("StubSpec", (), {"environment_digest": "b" * 64})()
        self.diverge = diverge
        self.replays = 0
        self.steps = 0
        self.reset(0)

    def reset(self, seed):
        self.steps = 0
        self.value = 0
        self.seen = []
        return {"sample": 0.0}

    def preview(self):
        return {
            "render_kind": "actual_native_frame_preview",
            "source_pixel_digest": "c" * 64,
            "width": 2,
            "height": 2,
        }

    def step(self, action):
        self.steps += 1
        self.seen.append(action)
        self.value += {"idle": 0, "a": 1}[action]
        if self.diverge and self.replays:
            self.value += 1
        observation = {"sample": float(self.value)}
        receipt = signature({"steps": self.steps, "value": self.value, "actions": self.seen})
        return type("Step", (), {
            "observation": observation,
            "reward_components": {"visual_change": 0.5},
            "transition_digest": receipt,
        })()

    def snapshot(self):
        return {
            "value": self.value, "steps": self.steps, "seen": list(self.seen),
            "snapshot_digest": signature({
                "value": self.value, "steps": self.steps, "seen": self.seen,
            }),
        }

    def restore(self, state):
        self.value = state["value"]
        self.steps = state["steps"]
        self.seen = list(state["seen"])
        self.replays += 1
        return {"sample": float(self.value)}

    def close(self):
        pass


class RegistryStub:
    registry_digest = "d" * 64


class FirstBootMatrixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.rom_path = Path(self.temp.name) / "original.gb"
        self.rom_path.write_bytes(b"original owned homebrew source")
        self.case = {
            "core_id": "gambatte",
            "target_id": "game_boy",
            "rom_path": str(self.rom_path),
            "filename": "original.gb",
            "rom_sha256": checksum(self.rom_path.read_bytes()),
        }

    def test_manifest_requires_flat_exact_hash_and_no_duplicates(self):
        location = Path(self.temp.name) / "manifest.json"
        location.write_text(json.dumps({
            "schema_version": SCHEMA, "cases": [self.case],
        }))
        self.assertEqual(_manifest(location), [self.case])
        location.write_text(json.dumps({
            "schema_version": SCHEMA, "cases": [self.case, self.case],
        }))
        with self.assertRaises(FirstBootError):
            _manifest(location)

    def test_two_physical_actions_and_true_snapshot_rewind_are_required(self):
        with patch(
            "skeleton.jeeves.game_emulator_host.create_emulator_environment",
            return_value=StubNativeHost(),
        ):
            receipt = _run_case(self.case, RegistryStub.registry_digest, timeout=5.0)
        self.assertTrue(receipt["actual_native_boot"])
        self.assertEqual(receipt["actual_emulator_steps"], 3)
        self.assertEqual(
            receipt["source_before_rewind_sha256"],
            receipt["source_after_rewind_sha256"],
        )
        self.assertEqual(
            receipt["second_transition_digest"],
            receipt["replayed_transition_digest"],
        )
        self.assertFalse(receipt["hardware_accuracy_certified"])

    def test_replay_divergence_is_not_a_successful_core(self):
        with patch(
            "skeleton.jeeves.game_emulator_host.create_emulator_environment",
            return_value=StubNativeHost(diverge=True),
        ):
            with self.assertRaises(FirstBootError):
                _run_case(self.case, RegistryStub.registry_digest, timeout=5.0)

    def test_fleet_reports_individual_failure_without_marking_ready(self):
        other = {**self.case, "core_id": "sameboy"}
        with patch(
            "skeleton.jeeves.game_emulator_catalog.GameEmulatorRegistry.from_environment",
            return_value=RegistryStub(),
        ), patch(
            "skeleton.jeeves.game_emulator_host.create_emulator_environment",
            side_effect=[StubNativeHost(), ValueError("approved core absent")],
        ):
            report = run_matrix([self.case, other], rights_acknowledged=True)
        self.assertEqual(report["actual_verified_first_boots"], 1)
        self.assertEqual(report["unverified_or_failed_cases"], 1)
        self.assertFalse(report["all_cases_passed"])
        self.assertFalse(report["promotion_authorized"])
        self.assertEqual(report["cases"][1]["status"], "first_boot_rejected")

    def test_explicit_rights_and_rom_integrity_are_mandatory(self):
        with self.assertRaises(FirstBootError):
            run_matrix([self.case], rights_acknowledged=False)
        mismatch = {**self.case, "rom_sha256": "0" * 64}
        with self.assertRaises(FirstBootError):
            _run_case(mismatch, RegistryStub.registry_digest, timeout=5.0)


if __name__ == "__main__":
    unittest.main()
