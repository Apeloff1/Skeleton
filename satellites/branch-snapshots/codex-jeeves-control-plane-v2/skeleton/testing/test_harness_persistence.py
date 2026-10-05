"""Tests for harness persistence wiring."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path


class TestHarnessPersistence(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_snapshot_and_restore_cycle(self):
        from skeleton.deploy.harness import Harness

        h1 = Harness(seed=42, snapshot_root=str(self.tmp))
        h1.boot()
        h1.genesis.get("quad").ingest_document("h-doc", "The Forge produces blueprints.")
        captured = h1.snapshot_state()
        self.assertGreater(captured["planes"]["kag"], 0)

        h2 = Harness(seed=42, snapshot_root=str(self.tmp))
        h2.boot(restore=True)
        kag = h2.genesis.get("quad")._planes["kag"]
        self.assertGreater(kag.graph.stats()["triples"], 0)

    def test_restore_without_snapshot_is_noop(self):
        from skeleton.deploy.harness import Harness

        h = Harness(seed=42, snapshot_root=str(self.tmp))
        h.boot(restore=True)
        kag = h.genesis.get("quad")._planes["kag"]
        self.assertEqual(kag.graph.stats()["triples"], 0)

    def test_named_snapshots_isolated(self):
        from skeleton.deploy.harness import Harness

        h1 = Harness(seed=42, snapshot_root=str(self.tmp))
        h1.boot()
        h1.genesis.get("quad").ingest_document("a-doc", "Alpha is a beta.")
        h1.snapshot_state(name="alpha")

        h2 = Harness(seed=42, snapshot_root=str(self.tmp))
        h2.boot()
        h2.genesis.get("quad").ingest_document("b-doc", "Gamma uses delta.")
        h2.snapshot_state(name="beta")

        h3 = Harness(seed=42, snapshot_root=str(self.tmp))
        h3.boot()
        restored = h3.restore_state(name="alpha")
        self.assertGreater(restored.get("kag", 0), 0)
        kag = h3.genesis.get("quad")._planes["kag"]
        entities = kag.graph.find_entities("alpha beta")
        self.assertIn("alpha", [e.lower() for e in entities])

    def test_shutdown_snapshots_state(self):
        from skeleton.deploy.harness import Harness

        h = Harness(seed=42, snapshot_root=str(self.tmp))
        h.boot()
        h.genesis.get("quad").ingest_document("sd-doc", "Shutdown persists state.")
        h.shutdown(snapshot=True)

        from skeleton.persistence import SnapshotStore
        store = SnapshotStore(self.tmp)
        self.assertIsNotNone(store.load("genesis-kag"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
