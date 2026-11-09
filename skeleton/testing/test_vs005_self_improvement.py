from __future__ import annotations
import hashlib
import unittest
from skeleton.eval.vertical_suite import ImprovementCandidate, SelfImprovementFixture, VerticalSuiteError

class VS005SelfImprovementTests(unittest.TestCase):
    def _candidate(self):
        return ImprovementCandidate(
            "cand-1",
            hashlib.sha256(b"champion").hexdigest(),
            hashlib.sha256(b"challenger").hexdigest(),
            "sandbox:isolated",
            ("quality","safety","cost","robustness"),
        )

    def test_independent_promotion_and_executable_rollback(self):
        fixture=SelfImprovementFixture()
        decision=fixture.decide(
            self._candidate(),
            metric_results={"quality":0.1,"safety":0.1,"cost":0.1,"robustness":0.1},
            implementer_id="trainer",
            verifier_id="independent",
            evaluation_refs=("eval:heldout","eval:red-team"),
            canary_ref="canary:1",
            rollback_ref="rollback:1",
        )
        self.assertTrue(decision.promoted)
        rollback=fixture.rollback(self._candidate(),reason="canary regression")
        self.assertNotEqual(rollback.from_digest,rollback.to_digest)

    def test_self_promotion_is_rejected(self):
        with self.assertRaisesRegex(VerticalSuiteError,"independent"):
            SelfImprovementFixture().decide(
                self._candidate(),
                metric_results={"quality":0.1,"safety":0.1,"cost":0.1,"robustness":0.1},
                implementer_id="same",
                verifier_id="same",
                evaluation_refs=("eval:a","eval:b"),
                canary_ref="canary:1",
                rollback_ref="rollback:1",
            )

if __name__=="__main__": unittest.main()
