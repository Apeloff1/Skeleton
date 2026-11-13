"""Deterministic review-to-playable delivery contract regression tests."""
from __future__ import annotations

import copy
import unittest
from tempfile import TemporaryDirectory

from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, propose,
)
from skeleton.jeeves.worlds.world_handoff_cli import verify_handoff
from skeleton.jeeves.worlds.world_reviewed_delivery import (
    preview, publish_approved,
)


class ReviewedDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.world = propose(
            world_id="reviewed", premise="An original expedition.",
            protagonist="Ari", region="North Vale", goal="Reach the summit",
        )
        self.store = WorldStore(self.root)
        self.initial = self.store.publish(self.world, create=True)
        self.operation = {
            "action": "replace_scene",
            "value": {
                "id": "opening", "title": "Ari at the crossroads",
                "narrative": "A new original route opens.",
            },
        }

    def approve(self):
        return preview(self.root, "reviewed", self.operation)

    def deliver(self, ticket):
        return publish_approved(
            self.root, "reviewed", self.operation,
            expected_digest=ticket.expected_digest,
            approved_digest=ticket.candidate_digest,
        )

    def test_preview_is_read_only(self):
        ticket = self.approve()
        self.assertEqual(digest(self.store.read("reviewed")), self.initial)
        self.assertEqual(ticket.expected_digest, self.initial)
        self.assertNotEqual(ticket.candidate_digest, self.initial)
        self.assertEqual(ticket.proof["source_digest"], ticket.candidate_digest)

    def test_approved_delivery_is_portable_and_verified(self):
        ticket = self.approve()
        result = self.deliver(ticket)
        self.assertEqual(result["published_digest"], ticket.candidate_digest)
        self.assertEqual(digest(self.store.read("reviewed")), ticket.candidate_digest)
        verified = verify_handoff(canonical(result["handoff"]))
        self.assertEqual(verified["source_digest"], ticket.candidate_digest)

    def test_missing_approval_fails_without_mutation(self):
        ticket = self.approve()
        for wrong in ("", "X" * 64, "0" * 64, None):
            with self.subTest(wrong=wrong), self.assertRaises(CanonError):
                publish_approved(
                    self.root, "reviewed", self.operation,
                    expected_digest=ticket.expected_digest,
                    approved_digest=wrong,
                )
            self.assertEqual(digest(self.store.read("reviewed")), self.initial)

    def test_changed_candidate_is_not_approved(self):
        ticket = self.approve()
        changed = copy.deepcopy(self.operation)
        changed["value"]["narrative"] = "A different unreviewed route."
        with self.assertRaisesRegex(CanonError, "review_mismatch"):
            publish_approved(
                self.root, "reviewed", changed,
                expected_digest=ticket.expected_digest,
                approved_digest=ticket.candidate_digest,
            )
        self.assertEqual(digest(self.store.read("reviewed")), self.initial)

    def test_stale_lease_fails_closed(self):
        ticket = self.approve()
        self.deliver(ticket)
        with self.assertRaisesRegex(CanonError, "stale_source"):
            self.deliver(ticket)

    def test_invalid_edit_does_not_publish(self):
        ticket = self.approve()
        invalid = {"action": "remove_scene", "value": {"id": "opening"}}
        with self.assertRaises(CanonError):
            publish_approved(
                self.root, "reviewed", invalid,
                expected_digest=ticket.expected_digest,
                approved_digest=ticket.candidate_digest,
            )
        self.assertEqual(digest(self.store.read("reviewed")), self.initial)


if __name__ == "__main__":
    unittest.main()
