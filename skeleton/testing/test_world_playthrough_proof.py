"""Positive, negative and reopened-store playthrough proof regression."""
import tempfile
import unittest

from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, compile_html, propose, digest,
)
from skeleton.jeeves.worlds.playthrough_proof import verify_playthrough, replay_checkpoint
from hashlib import sha256


class PlaythroughProofTests(unittest.TestCase):
    def setUp(self):
        self.world = propose(world_id="test-world", premise="Find the beacon",
                             protagonist="Ada", region="Vale", goal="Light the beacon")
        self.sha = digest(self.world)

    def verify(self, trace, **kwargs):
        return verify_playthrough(self.world, trace,
                                  expected_source_sha=self.sha, **kwargs)

    def test_completed_original_ending(self):
        result = self.verify(["pursue_goal"])
        self.assertEqual(result["ending_scene"], "resolution")
        self.assertEqual(result["choice_count"], 1)

    def test_export_binding(self):
        html = sha256(compile_html(self.world).encode()).hexdigest()
        self.assertEqual(self.verify(["pursue_goal"], expected_html_sha=html)["export_digest"], html)
        with self.assertRaisesRegex(CanonError, "export_mismatch"):
            self.verify(["pursue_goal"], expected_html_sha="0" * 64)

    def test_reject_incomplete_unknown_and_extra_actions(self):
        for trace in ([], ["missing"], ["pursue_goal", "pursue_goal"], [True], "pursue_goal"):
            with self.subTest(trace=trace), self.assertRaises(CanonError):
                self.verify(trace)

    def test_stale_revision_fails_closed(self):
        with self.assertRaisesRegex(CanonError, "stale_source"):
            verify_playthrough(self.world, ["pursue_goal"], expected_source_sha="0" * 64)

    def test_checkpoint_replay_and_resume(self):
        opening = replay_checkpoint(self.world, [], expected_source_sha=self.sha)
        self.assertEqual(opening["scene"], "opening")
        self.assertFalse(opening["finished"])
        finished = replay_checkpoint(self.world, ["pursue_goal"],
                                     expected_source_sha=self.sha,
                                     previous_checkpoint=opening)
        self.assertTrue(finished["finished"])
        self.assertEqual(finished["scene"], "resolution")

    def test_checkpoint_tamper_stale_and_divergence(self):
        opening = replay_checkpoint(self.world, [], expected_source_sha=self.sha)
        corrupted = dict(opening, scene="resolution")
        for checkpoint, trace in ((corrupted, ["pursue_goal"]),
                                  (opening, [])):
            if checkpoint is opening:
                continue
            with self.assertRaisesRegex(CanonError, "checkpoint_tampered"):
                replay_checkpoint(self.world, trace,
                                  expected_source_sha=self.sha,
                                  previous_checkpoint=checkpoint)
        finished = replay_checkpoint(self.world, ["pursue_goal"],
                                     expected_source_sha=self.sha)
        with self.assertRaisesRegex(CanonError, "checkpoint_divergence"):
            replay_checkpoint(self.world, [], expected_source_sha=self.sha,
                              previous_checkpoint=finished)
        with self.assertRaisesRegex(CanonError, "stale_source"):
            replay_checkpoint(self.world, [], expected_source_sha="0" * 64)
        with self.assertRaisesRegex(CanonError, "invalid_trace"):
            replay_checkpoint(self.world, [True], expected_source_sha=self.sha)

    def test_reopen_persisted_world(self):
        with tempfile.TemporaryDirectory() as folder:
            store = WorldStore(folder)
            store.publish(self.world, create=True)
            reopened = WorldStore(folder)
            proof = verify_playthrough(reopened.read("test-world"),
                                       ["pursue_goal"], expected_source_sha=self.sha)
            self.assertEqual(proof["world_id"], "test-world")


if __name__ == "__main__":
    unittest.main()
