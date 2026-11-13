"""Regression for identity-fenced canonical world publication across reopen."""
from __future__ import annotations

import tempfile
import unittest

from skeleton.jeeves.worlds.world_canon import (
    CanonError, WorldStore, canonical, digest, propose,
)


class WorldIdentityFenceTests(unittest.TestCase):
    def test_cas_rejects_foreign_world_and_recovers_without_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            store = WorldStore(root)
            original = propose(world_id="home", premise="A new journey",
                               protagonist="Ari", region="River", goal="Return")
            source_digest = store.publish(original, create=True)
            foreign = propose(world_id="other", premise="A different journey",
                              protagonist="Bea", region="Forest", goal="Escape")
            fd = store._directory()
            try:
                store._write(fd, "home.json", canonical(foreign))
            finally:
                import os
                os.close(fd)
            reopened = WorldStore(root)
            with self.assertRaises(CanonError) as raised:
                reopened.publish(original, expected_digest=digest(foreign))
            self.assertEqual(raised.exception.code, "identity_mismatch")
            fd = reopened._directory()
            try:
                self.assertEqual(reopened._read(fd, "home.json"), canonical(foreign))
                reopened._write(fd, "home.json", canonical(original))
            finally:
                import os
                os.close(fd)
            self.assertEqual(reopened.publish(original, expected_digest=source_digest),
                             source_digest)
            self.assertEqual(WorldStore(root).read("home")["id"], "home")

    def test_normal_create_and_stale_cas_remain_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            store = WorldStore(root)
            world = propose(world_id="home", premise="A new journey",
                            protagonist="Ari", region="River", goal="Return")
            current = store.publish(world, create=True)
            with self.assertRaises(CanonError) as raised:
                store.publish(world, expected_digest="0" * 64)
            self.assertEqual(raised.exception.code, "stale_source")
            self.assertEqual(store.publish(world, expected_digest=current), current)


if __name__ == "__main__":
    unittest.main()
