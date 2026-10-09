import unittest

from ai_tree_fill.capability_body import CapabilityBody, run_body
from ai_tree_fill.catalog import DESCRIPTORS


class CapabilityBodyTests(unittest.TestCase):
    def test_every_catalog_id_has_a_body(self):
        body = CapabilityBody()
        cards = body.invoke_all()
        self.assertEqual(set(cards), {item.capability_id for item in DESCRIPTORS})
        unknown = [cid for cid, card in cards.items() if card.get("law") == "unknown-capability"]
        self.assertEqual(unknown, [])
        self.assertEqual(cards["AIFT-DECISION"]["pick_used"], False)
        self.assertEqual(cards["AIFT-RUNTIME-CONTRACTS"]["hit"], 0)
        self.assertEqual(cards["AIFT-EVIDENCE"]["availability"], "unavailable")
        self.assertEqual(cards["AIFT-TRAINING"]["absorb_steps"], 4)

    def test_run_body_signs_the_set(self):
        report = run_body()
        self.assertGreaterEqual(report["capabilities"], 48)
        self.assertEqual(len(report["key_id"]), 64)
        self.assertGreater(report["hit"], 40)


if __name__ == "__main__":
    unittest.main()
