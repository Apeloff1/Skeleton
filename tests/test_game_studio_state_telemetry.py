"""Reference telemetry pixels are actual state-derived and replay deterministic."""
from __future__ import annotations

import base64
from hashlib import sha256
import unittest

from skeleton.jeeves.game_studio_environment import (
    StudioGameEnvironment, make_studio_source,
)


class SourceTelemetryTests(unittest.TestCase):
    def test_same_replay_restores_identical_measured_raster(self):
        source=make_studio_source("platform_profile",actions=("inspect","frame"))
        env=StudioGameEnvironment(source,max_steps=4)
        env.reset(5)
        first=env.preview()
        self.assertEqual(first["render_kind"],"reference_state_telemetry_raster")
        self.assertTrue(first["telemetry_raster_available"])
        self.assertFalse(first["pixel_frame_available"])
        raw=base64.b64decode(first["pixels_base64"],validate=True)
        self.assertEqual(len(raw),96*64*3)
        self.assertEqual(sha256(raw).hexdigest(),first["pixel_digest"])
        step=env.step("frame")
        self.assertTrue(step.info["evidence"]["accepted"])
        last=env.preview()
        self.assertNotEqual(first["pixel_digest"],last["pixel_digest"])
        saved=env.snapshot()
        same=StudioGameEnvironment(source,max_steps=4)
        same.restore(saved)
        self.assertEqual(last,same.preview())
        self.assertFalse(last["real_game_world_framebuffer"])
        self.assertFalse(last["native_hardware_verified"])
        env.close()
        same.close()

    def test_metrics_are_real_not_arbitrary_player_submitted_pixels(self):
        source=make_studio_source("economy",actions=("inspect","survey"))
        env=StudioGameEnvironment(source,max_steps=5)
        env.reset(6)
        image=env.preview()
        self.assertEqual(image["source_session_digest"],
                         env.snapshot()["source_session_digest"])
        self.assertNotIn("frame_source_code",image)
        self.assertEqual(len(image["metric_keys"]),7)
        self.assertEqual(image["accepted_action_count"],0)
        env.close()


if __name__=="__main__":
    unittest.main()
