import unittest

from ai_tree_fill.replay_verifier import replay, sign_replay, verify_replay
from ai_tree_fill.trials import run_trials, write_log


class CloseoutTests(unittest.TestCase):
    def test_trials_are_unique_and_replay_signs_a_different_role(self):
        records = run_trials(48)
        stimuli = [row["stimulus"] for row in records if not row["expect_fail"]]
        self.assertEqual(len(stimuli), len(set(stimuli)))
        path = "/tmp/aitree_build/trials.json"
        write_log(path, records)
        report = replay({"records": records, "log_digest": __import__("json").load(open(path))["log_digest"]})
        self.assertGreaterEqual(report["unique_stimuli"], 48)
        self.assertGreaterEqual(report["negatives"], 5)
        signature = sign_replay(report, "9d4a652d")
        self.assertEqual(signature["role"], "independent_verification")
        self.assertNotEqual(signature["signer_id"], "p5-adversarial-verifier")
        self.assertNotIn("private_key_hex", signature)
        self.assertTrue(verify_replay(report, signature, "9d4a652d"))


if __name__ == "__main__":
    unittest.main()
