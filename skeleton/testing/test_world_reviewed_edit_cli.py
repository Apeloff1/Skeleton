"""Deterministic operator review and source-lease acceptance tests."""
from __future__ import annotations

import io
import json
import tempfile
import unittest

from skeleton.jeeves.worlds.world_canon import WorldStore, digest, propose
from skeleton.jeeves.worlds.world_edit_cli import run


class ReviewedWorldEditTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.world = propose(world_id="review_world", premise="An original passage.",
                             protagonist="Mira", region="Vale", goal="Find the summit")
        self.store = WorldStore(self.directory.name)
        self.store.publish(self.world, create=True)
        self.operation = {"action": "replace_scene", "value": {
            "id": "opening", "title": "A reviewed new beginning",
            "narrative": "A new path through the valley."}}

    def invoke(self, action, payload=None, *, expected=None, reviewed=None):
        argv = ["--root", self.directory.name, "--world-id", "review_world"]
        if expected is not None:
            argv += ["--expected-digest", expected]
        if reviewed is not None:
            argv += ["--reviewed-digest", reviewed]
        argv += [action]
        output, errors = io.BytesIO(), io.StringIO()
        raw = json.dumps(self.operation if payload is None else payload).encode()
        status = run(argv, input_stream=io.BytesIO(raw),
                     output_stream=output, error_stream=errors)
        return status, (json.loads(output.getvalue()) if output.getvalue() else None), (
            json.loads(errors.getvalue()) if errors.getvalue() else None)

    def test_preview_is_read_only_and_commit_requires_exact_review(self):
        before = digest(self.store.read("review_world"))
        status, preview, error = self.invoke("preview", expected=before)
        self.assertEqual((status, error), (0, None))
        self.assertEqual(preview["previous_digest"], before)
        self.assertNotEqual(preview["candidate_digest"], before)
        self.assertEqual(digest(self.store.read("review_world")), before)
        status, committed, error = self.invoke(
            "commit", expected=before, reviewed=preview["candidate_digest"])
        self.assertEqual((status, error), (0, None))
        self.assertEqual(committed["candidate_digest"], preview["candidate_digest"])
        self.assertEqual(digest(self.store.read("review_world")), preview["candidate_digest"])

    def test_no_review_is_rejected_without_mutation(self):
        before = digest(self.store.read("review_world"))
        status, output, error = self.invoke("commit", expected=before)
        self.assertEqual((status, output, error), (2, None, {"error": "review_required"}))
        self.assertEqual(digest(self.store.read("review_world")), before)

    def test_review_mismatch_rejected_without_mutation(self):
        before = digest(self.store.read("review_world"))
        status, output, error = self.invoke(
            "commit", expected=before, reviewed="0" * 64)
        self.assertEqual((status, output, error), (2, None, {"error": "review_mismatch"}))
        self.assertEqual(digest(self.store.read("review_world")), before)

    def test_stale_source_is_rejected(self):
        before = digest(self.store.read("review_world"))
        status, preview, _ = self.invoke("preview", expected=before)
        changed = dict(self.world)
        changed["prompt"] = "An independently published source revision."
        self.store.publish(changed, expected_digest=before)
        status, output, error = self.invoke(
            "commit", expected=before, reviewed=preview["candidate_digest"])
        self.assertEqual((status, output, error), (2, None, {"error": "stale_source"}))

    def test_invalid_edit_and_oversize_fail_closed(self):
        before = digest(self.store.read("review_world"))
        for raw in (b'{"action":"batch","value":[]}',
                    b'{"action":"batch","action":"batch","value":[]}',
                    b" " * 65537):
            output, errors = io.BytesIO(), io.StringIO()
            status = run(["--root", self.directory.name, "--world-id",
                          "review_world", "preview"], input_stream=io.BytesIO(raw),
                         output_stream=output, error_stream=errors)
            self.assertEqual(status, 2)
            self.assertEqual(output.getvalue(), b"")
            self.assertTrue(json.loads(errors.getvalue())["error"])
        self.assertEqual(digest(self.store.read("review_world")), before)

    def test_nonbinary_input_rejected(self):
        output, errors = io.BytesIO(), io.StringIO()
        status = run(["--root", self.directory.name, "--world-id", "review_world",
                      "preview"], input_stream=io.StringIO("{}"),
                     output_stream=output, error_stream=errors)
        self.assertEqual(status, 2)
        self.assertEqual(json.loads(errors.getvalue()), {"error": "invalid_edit_payload"})


if __name__ == "__main__":
    unittest.main()
