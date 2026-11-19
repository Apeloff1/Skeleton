"""GB-27 accept tests. Both SKELETON_OWN gates."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from skeleton.persist import Persist, PersistEngine, capabilities
from skeleton.persist.verify import run_all


class TestLocalGate(unittest.TestCase):
    def test_unset_is_process_local(self) -> None:
        p = Persist(env={})
        p.put("deck", "k", "v")
        p.put("jeeves", "j", "1")
        self.assertEqual(p.gate(), "local")
        self.assertTrue(p.has_local("deck", "k"))
        self.assertTrue(p.has_local("jeeves", "j"))
        self.assertFalse(any(p.disk_paths().values()))


class TestDiskGate(unittest.TestCase):
    def test_set_writes_helix_rotors_traces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Persist(env={"SKELETON_OWN": tmp})
            p.put("helix", "obs", "1")
            p.put("rotors", "r0", "on")
            p.put("traces", "t0", "ok")
            self.assertEqual(p.gate(), "disk")
            root = Path(tmp)
            self.assertTrue((root / "helix.jsonl").exists())
            self.assertTrue((root / "rotors.json").exists())
            self.assertTrue((root / "traces" / "t0.txt").exists())


class TestCaps(unittest.TestCase):
    def test_one_core_and_engine(self) -> None:
        self.assertEqual(capabilities()["contract"]["cores"], 1)
        snap = PersistEngine().snapshot()
        self.assertEqual(snap["hit"], 1)
        self.assertEqual(snap["stored_prose"], 0)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(run_all(tmp)["failed"], [])


if __name__ == "__main__":
    unittest.main()
