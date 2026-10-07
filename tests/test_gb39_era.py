"""GB-39 era-bind tests."""

from __future__ import annotations

import unittest

from skeleton.era import HOUSE_ERA, capabilities, era_bind, forge


class TestBind(unittest.TestCase):
    def test_forge_extraction_cites(self) -> None:
        card = forge("extraction")
        self.assertEqual(card["reference"], "era_bind")
        self.assertIn("citation", card["reference_card"])
        self.assertEqual(card["stored_prose"], 0)
        self.assertIsNone(card["project_root"])

    def test_cut_then_plan(self) -> None:
        era_bind.cut("NAMED_ERA")
        planned = era_bind.plan()
        self.assertEqual(planned["era"], "NAMED_ERA")
        era_bind.cut(HOUSE_ERA)
        self.assertEqual(era_bind.plan()["era"], HOUSE_ERA)

    def test_like_title(self) -> None:
        self.assertEqual(era_bind.resolve("house")["era"], HOUSE_ERA)

    def test_caps(self) -> None:
        cap = capabilities()
        self.assertEqual(cap["contract"]["forge_requires_citation"], 1)


if __name__ == "__main__":
    unittest.main()
