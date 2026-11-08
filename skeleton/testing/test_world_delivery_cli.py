"""Deterministic operator journey: preview -> approval -> playable handoff."""
from __future__ import annotations

import io
import json
import unittest
from tempfile import TemporaryDirectory

from skeleton.jeeves.worlds.world_canon import WorldStore, canonical, digest, propose
from skeleton.jeeves.worlds.world_delivery_cli import MAX_OPERATION_BYTES, run
from skeleton.jeeves.worlds.world_handoff_cli import verify_handoff


class DeliveryJourneyTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = self.temp.name
        self.world = propose(world_id="journey", premise="A new original valley.",
                             protagonist="Ari", region="Valley", goal="Find the gate")
        self.store = WorldStore(self.root)
        self.original = self.store.publish(self.world, create=True)
        self.operation = {"action": "replace_scene", "value": {
            "id": "opening", "title": "Ari reaches the valley",
            "narrative": "A unique and peaceful valley appears."}}

    def invoke(self, action, operation=None, extra=(), raw=None):
        out, err = io.BytesIO(), io.StringIO()
        payload = canonical(self.operation if operation is None else operation) if raw is None else raw
        status = run([action, "--root", self.root, "--world-id", "journey", *extra],
                     input_stream=io.BytesIO(payload), output_stream=out, error_stream=err)
        return status, out.getvalue(), err.getvalue()

    def test_preview_publish_and_verify_playable(self):
        status, raw, error = self.invoke("preview")
        self.assertEqual((status, error), (0, ""))
        ticket = json.loads(raw)
        self.assertEqual(ticket["expected_digest"], self.original)
        self.assertEqual(digest(self.store.read("journey")), self.original)
        status, raw, error = self.invoke("publish", extra=(
            "--expected-digest", ticket["expected_digest"],
            "--approved-digest", ticket["candidate_digest"]))
        self.assertEqual((status, error), (0, ""))
        delivery = json.loads(raw)
        self.assertEqual(delivery["published_digest"], ticket["candidate_digest"])
        self.assertEqual(verify_handoff(canonical(delivery["handoff"]))["source_digest"],
                         ticket["candidate_digest"])

    def test_publish_requires_explicit_approval(self):
        status, raw, error = self.invoke("publish")
        self.assertEqual((status, raw), (2, b""))
        self.assertIn("review_required", error)
        self.assertEqual(digest(self.store.read("journey")), self.original)

    def test_changed_operation_is_not_approved(self):
        ticket = json.loads(self.invoke("preview")[1])
        changed = {"action": "replace_scene", "value": dict(self.operation["value"])}
        changed["value"]["narrative"] = "Unreviewed replacement"
        status, raw, error = self.invoke("publish", changed, (
            "--expected-digest", ticket["expected_digest"],
            "--approved-digest", ticket["candidate_digest"]))
        self.assertEqual((status, raw), (2, b""))
        self.assertIn("review_mismatch", error)
        self.assertEqual(digest(self.store.read("journey")), self.original)

    def test_stale_revision_rejected(self):
        ticket = json.loads(self.invoke("preview")[1])
        args = ("--expected-digest", ticket["expected_digest"],
                "--approved-digest", ticket["candidate_digest"])
        self.assertEqual(self.invoke("publish", extra=args)[0], 0)
        self.assertIn("stale_source", self.invoke("publish", extra=args)[2])

    def test_preview_cannot_accept_approval(self):
        status, raw, error = self.invoke("preview", extra=("--approved-digest", "0" * 64))
        self.assertEqual((status, raw), (2, b""))
        self.assertIn("approval_not_accepted_in_preview", error)

    def test_bounded_and_malformed_operations(self):
        for raw in (b"x" * (MAX_OPERATION_BYTES + 1), b"{", b"[]",
                    b'{"action":"batch","action":"batch","value":[]}'):
            with self.subTest(raw=raw[:20]):
                status, output, error = self.invoke("preview", raw=raw)
                self.assertEqual((status, output), (2, b""))
                self.assertTrue(error)
                self.assertEqual(digest(self.store.read("journey")), self.original)


if __name__ == "__main__":
    unittest.main()
