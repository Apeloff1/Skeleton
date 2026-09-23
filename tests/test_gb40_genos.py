"""GB-40 DNAHelix / genos tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from skeleton.genos import DNAHelix, Genos, capabilities


class TestCoil(unittest.TestCase):
    def test_forge_then_genos(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            g = Genos(DNAHelix(Path(td)))
            card = g.forge_emit("extraction")
            self.assertGreaterEqual(card["n"], 1)
            self.assertEqual(card["stored_prose"], 0)
            self.assertTrue(Path(card["path"]).exists())

    def test_caps(self) -> None:
        cap = capabilities()
        self.assertEqual(cap["contract"]["chain"], 0)
        self.assertEqual(cap["contract"]["genome_prose"], 0)


if __name__ == "__main__":
    unittest.main()
