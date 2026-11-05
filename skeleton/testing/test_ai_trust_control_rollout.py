"""Executable state-machine and fail-closed regression tests."""
from skeleton.ai.runtime.operational_ai.trust_gates.control.model_epoch import ModelEpoch
from skeleton.ai.runtime.operational_ai.trust_gates.control.rollout import ModelRollout
from skeleton.ai.runtime.operational_ai.trust_gates.applications.release_evidence import REQUIRED
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
import unittest
class TestRollout(unittest.TestCase):
    def test_staged_approved_rollout_and_rollback(self):
        runner=ModelRollout(ModelEpoch("a"*64,"a"*64))
        runner.stage(model_sha="b"*64,tokenizer_sha="b"*64,head_sha="c"*64,
            observed={name:"success" for name in REQUIRED},reviewed=True,
            real_e2e=True,rights=True,installation=True)
        with self.assertRaises(GateViolation):runner.commit()
        self.assertEqual(runner.commit(approved=True)[1],"b"*64)
        self.assertEqual(runner.rollback(approved=True)[1],"a"*64)
    def test_incomplete_ci_refused(self):
        runner=ModelRollout(ModelEpoch("a"*64,"a"*64))
        statuses={name:"success" for name in REQUIRED}
        statuses["Malware Gate"]="pending"
        with self.assertRaises(GateViolation):
            runner.stage(model_sha="b"*64,tokenizer_sha="b"*64,head_sha="c"*64,
                observed=statuses,reviewed=True,real_e2e=True,rights=True,installation=True)

if __name__=="__main__":
    unittest.main()
