"""Source-only bounded native time control and paused RGB inspection contracts.

No game ROM, real libretro core, training or hardware-fidelity claim.
"""
from __future__ import annotations

import hashlib
import threading
import unittest

from skeleton.jeeves.game_emulator_timing import (
    normalize_timing, native_execution_budget, inspect_rgb_frame,
)
from skeleton.jeeves.game_emulator_host import EmulatorEnvironment, EmulatorHostError


class NativeTimePolicyContracts(unittest.TestCase):
    def test_every_profile_uses_finite_frames_or_zero_when_frozen(self):
        self.assertEqual(native_execution_budget("paused", 0, 3), (0, 0))
        for factor in (2, 4, 8):
            self.assertEqual(native_execution_budget("slow", factor, 12), (1, 1))
            self.assertEqual(native_execution_budget("fast", factor, 12), (12, factor))
        self.assertEqual(native_execution_budget("normal", 1, 12), (12, 1))

    def test_inadmissible_speed_profiles_fail_closed(self):
        for mode, factor in (
            ("paused", 1), ("fast", 16), ("slow", 0),
            ("normal", 2), ("rewind", 1), (True, 2),
            ("fast", True), ("fast", 2.0), ("slow", -1),
        ):
            with self.subTest(mode=mode, factor=factor):
                with self.assertRaises(ValueError):
                    normalize_timing(mode, factor)

    def test_fast_burst_does_not_change_core_frames_per_native_step(self):
        self.assertEqual(native_execution_budget("fast", 8, 60), (60, 8))
        with self.assertRaises(ValueError):
            native_execution_budget("fast", 8, 61)

    def test_exact_rgb_tile_hashing_covers_all_pixels(self):
        pixels = bytes([3, 4, 5]) * (16 * 16)
        frame_sha = hashlib.sha256(pixels).hexdigest()
        report = inspect_rgb_frame(pixels, 16, 16, frame_sha, "a"*64, 7)
        self.assertEqual(report["total_tiles"], 256)
        self.assertEqual(report["native_frames_executed_for_inspection"], 0)
        self.assertEqual(report["tiles"][0]["tile_rgb_sha256"],
                         hashlib.sha256(bytes([3, 4, 5])).hexdigest())
        self.assertEqual(report["tiles"][0]["sampled_rgb_mean"], [3.0, 4.0, 5.0])
        self.assertTrue(report["full_resolution_tile_hashes"])
        self.assertTrue(report["tile_color_statistics_are_sampled"])

    def test_partial_tiles_cover_non_divisible_geometry(self):
        width, height = 23, 17
        pixels = bytes(range(256)) * 4 + bytes(range(3*width*height-1024))
        report = inspect_rgb_frame(pixels, width, height, hashlib.sha256(pixels).hexdigest(), "b"*64, 1)
        total = sum(t["width"]*t["height"] for t in report["tiles"])
        self.assertEqual(total, width*height)
        self.assertEqual(report["total_tiles"], 256)
        self.assertTrue(all(t["width"]>=1 and t["height"]>=1 for t in report["tiles"]))

    def test_corrupted_rgb_or_dimensions_rejected_before_capture(self):
        pixels = bytes([0, 1, 2]) * 64
        sha = hashlib.sha256(pixels).hexdigest()
        for packet in (
            (pixels, 8, 8, "0"*64, "a"*64, 1),
            (pixels[:-1], 8, 8, sha, "a"*64, 1),
            (pixels, 9, 8, sha, "a"*64, 1),
            (pixels, 8, 8, sha, "a"*64, -1),
        ):
            with self.subTest(packet=packet[1:3]), self.assertRaises(ValueError):
                inspect_rgb_frame(*packet)

    def test_frozen_host_audit_never_calls_worker(self):
        pixels = bytes([50, 100, 150]) * 4
        host = object.__new__(EmulatorEnvironment)
        host._lock = threading.RLock()
        host._seed = 1
        host._closed = False
        host._pixels = pixels
        host._frame = {
            "width": 2, "height": 2,
            "pixel_sha256": hashlib.sha256(pixels).hexdigest(),
            "audio_sha256": "a"*64, "runs": 12,
        }
        host._exchange = lambda *_args, **_kwargs: self.fail("Paused inspection must never call worker")
        before = dict(host._frame)
        report = host.inspect_frame()
        self.assertEqual(report["native_run_cursor"], 12)
        self.assertEqual(host._frame, before)
        self.assertEqual(report["total_tiles"], 4)
        host._pixels = None
        with self.assertRaises(EmulatorHostError):
            host.inspect_frame()

    def test_host_precise_step_is_strictly_bounded(self):
        host = object.__new__(EmulatorEnvironment)
        calls = []
        host._step = lambda controls, action, **kw: calls.append((controls, action, kw))
        controls=[{"buttons":0,"axes":[0,0,0,0],"keys":[],
                   "mouse":[0]*6,"pointer":[0]*3}]
        host.input_frame_step(controls, frames=1)
        host.input_frame_step(controls, frames=60)
        self.assertEqual([call[2]["frame_count"] for call in calls], [1, 60])
        for frames in (0, 61, True, -2, 1.5):
            with self.assertRaises((ValueError, EmulatorHostError)):
                host.input_frame_step(controls, frames=frames)
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
