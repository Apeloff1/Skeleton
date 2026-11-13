"""Regression: canonical session reads serialize with world writer publication."""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from skeleton.jeeves.worlds.session import SessionStore
from skeleton.jeeves.worlds.world_canon import CanonError, WorldStore, propose


class SessionSnapshotLeaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.worlds = WorldStore(self.temp.name)
        self.sessions = SessionStore(self.temp.name)
        self.worlds.publish(propose(
            world_id="lease_world", premise="Find the lost lantern",
            protagonist="Aster", region="The north marsh", goal="Light the tower"
        ), create=True)
        self.sessions.create("lease_world", "slot_a")

    def test_read_returns_consistent_replay_and_releases_lock(self):
        first = self.sessions.read("lease_world", "slot_a")
        self.assertEqual(first["revision"], 0)
        self.assertEqual(first["scene"], "opening")
        self.assertFalse(os.path.exists(os.path.join(self.temp.name, "lease_world.lock")))
        self.assertEqual(self.sessions.read("lease_world", "slot_a"), first)

    def test_snapshot_read_rejects_stale_world_cas(self):
        from skeleton.jeeves.worlds.world_canon import digest
        world = self.worlds.read("lease_world")
        current = digest(world)
        self.assertEqual(self.sessions.read("lease_world", "slot_a",
                                            expected_world_digest=current)["revision"], 0)
        with self.assertRaises(CanonError) as raised:
            self.sessions.read("lease_world", "slot_a",
                               expected_world_digest="0" * 64)
        self.assertEqual(raised.exception.code, "session_world_lease_mismatch")
        self.assertFalse(os.path.exists(os.path.join(self.temp.name, "lease_world.lock")))

    def test_snapshot_read_requires_source_guard_under_lease(self):
        seen = []
        def approve(fd, world_id):
            seen.append((world_id, os.path.exists(os.path.join(self.temp.name,
                                                              world_id + ".lock"))))
        self.sessions.read("lease_world", "slot_a", source_guard=approve)
        self.assertEqual(seen, [("lease_world", True)])
        def reject(fd, world_id):
            raise CanonError("source_not_approved")
        with self.assertRaises(CanonError) as raised:
            self.sessions.read("lease_world", "slot_a", source_guard=reject)
        self.assertEqual(raised.exception.code, "source_not_approved")
        self.assertFalse(os.path.exists(os.path.join(self.temp.name, "lease_world.lock")))
        self.assertEqual(self.sessions.read("lease_world", "slot_a")["revision"], 0)

    def test_busy_writer_fails_closed_without_removing_foreign_lock(self):
        path = os.path.join(self.temp.name, "lease_world.lock")
        with open(path, "xb") as handle:
            handle.write(b"foreign writer")
        with self.assertRaises(CanonError) as raised:
            self.sessions.read("lease_world", "slot_a")
        self.assertEqual(raised.exception.code, "lease_busy")
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), b"foreign writer")
        os.unlink(path)
        self.assertEqual(self.sessions.read("lease_world", "slot_a")["revision"], 0)

    def test_inspect_export_and_preflight_reject_busy_writer(self):
        from skeleton.jeeves.worlds.session import export_session
        world = self.worlds.read("lease_world")
        saved = self.sessions.read("lease_world", "slot_a")
        portable = export_session(saved, world)
        path = os.path.join(self.temp.name, "lease_world.lock")
        with open(path, "xb") as handle:
            handle.write(b"foreign writer")
        operations = (
            lambda: self.sessions.inspect("lease_world", "slot_a"),
            lambda: self.sessions.export("lease_world", "slot_a"),
            lambda: self.sessions.preflight_import("lease_world", portable),
        )
        for operation in operations:
            with self.subTest(operation=operation):
                with self.assertRaises(CanonError) as raised:
                    operation()
                self.assertEqual(raised.exception.code, "lease_busy")
                with open(path, "rb") as handle:
                    self.assertEqual(handle.read(), b"foreign writer")
        os.unlink(path)
        self.assertEqual(self.sessions.inspect("lease_world", "slot_a")["revision"], 0)
        self.assertEqual(self.sessions.export("lease_world", "slot_a"), portable)
        self.assertTrue(self.sessions.preflight_import("lease_world", portable)["restorable"])

    def test_inspect_replay_failure_releases_lease(self):
        with patch.object(self.sessions, "_session", side_effect=CanonError("simulated_corruption")):
            with self.assertRaises(CanonError) as raised:
                self.sessions.inspect("lease_world", "slot_a")
        self.assertEqual(raised.exception.code, "simulated_corruption")
        self.assertFalse(os.path.exists(os.path.join(self.temp.name, "lease_world.lock")))
        self.assertEqual(self.sessions.inspect("lease_world", "slot_a")["revision"], 0)

    def test_failed_replay_releases_owned_lock_and_preserves_save(self):
        path = os.path.join(self.temp.name, "lease_world.slot_a.session.json")
        with open(path, "rb") as handle:
            before = handle.read()
        with patch.object(self.sessions, "_session", side_effect=CanonError("simulated_corruption")):
            with self.assertRaises(CanonError) as raised:
                self.sessions.read("lease_world", "slot_a")
        self.assertEqual(raised.exception.code, "simulated_corruption")
        self.assertFalse(os.path.exists(os.path.join(self.temp.name, "lease_world.lock")))
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), before)
        self.assertEqual(self.sessions.read("lease_world", "slot_a")["revision"], 0)


if __name__ == "__main__":
    unittest.main()
