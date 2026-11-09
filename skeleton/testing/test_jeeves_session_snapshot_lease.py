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
