"""GB-28 helix jsonl tests. 3 appends, verify, tamper detect."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from skeleton.chronicle import ChronicleEngine, Helix, capabilities
from skeleton.chronicle.verify import run_all


class TestHelix(unittest.TestCase):
    def test_three_and_verify(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            h = Helix(Path(tmp) / "helix.jsonl")
            h.append("observe", "r1")
            h.append("forge", "r2")
            h.append("gossip", "r3")
            self.assertEqual(len(h.records()), 3)
            self.assertTrue(h.verify())

    def test_tamper_detect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "helix.jsonl"
            h = Helix(path)
            h.append("observe", "r1")
            h.append("forge", "r2")
            h.append("gossip", "r3")
            h.tamper(1, "evil")
            self.assertFalse(h.verify())


class TestCaps(unittest.TestCase):
    def test_engine(self) -> None:
        self.assertEqual(capabilities()["contract"]["coin"], 0)
        with tempfile.TemporaryDirectory() as tmp:
            snap = ChronicleEngine().snapshot(Path(tmp) / "e.jsonl")
            self.assertEqual(snap["hit"], 1)
            self.assertEqual(run_all(Path(tmp))["failed"], [])


if __name__ == "__main__":
    unittest.main()
