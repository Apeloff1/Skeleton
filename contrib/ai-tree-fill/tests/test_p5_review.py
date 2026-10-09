import unittest

from ai_tree_fill.catalog import DESCRIPTORS
from ai_tree_fill.laws import LawBreak
from ai_tree_fill.p5_verifier import mobile_bank, review, route, scan_secret, verify_signature


class P5ReviewTests(unittest.TestCase):
    def test_negatives_fail_closed(self):
        with self.assertRaises(LawBreak):
            scan_secret("-----BEGIN PRIVATE KEY-----")
        with self.assertRaises(LawBreak):
            mobile_bank("gpu")
        with self.assertRaises(LawBreak):
            route("shadow-router")

    def test_all_tasks_placed_and_signature_is_confirmed_only(self):
        result = review([d.capability_id for d in DESCRIPTORS])
        self.assertEqual(len([t for t in result.tasks if t.capability_id in {d.capability_id for d in DESCRIPTORS}]), len(DESCRIPTORS))
        self.assertTrue(all(task.place()["plane"] == "p5" for task in result.tasks))
        self.assertGreater(len(result.confirmed), 40)
        self.assertIn("P5-F13", result.withheld)
        self.assertNotIn("private_key_hex", result.signature)
        for cid in result.withheld:
            self.assertNotIn(cid, result.signature["signed_ids"])
        self.assertTrue(verify_signature(result.bundle, result.signature))


if __name__ == "__main__":
    unittest.main()
