from __future__ import annotations
import hashlib
import unittest
from skeleton.eval.vertical_suite import EngineeringAgentFixture, EngineeringTask, MutationLease, VerticalSuiteError

class VS002EngineeringAgentTests(unittest.TestCase):
    def test_bounded_plan_lease_independent_verification_and_rollback(self):
        task=EngineeringTask("eng-1","change one bounded fixture",("fixture/a.py",),hashlib.sha256(b"graph").hexdigest(),"rollback:eng-1")
        fixture=EngineeringAgentFixture()
        plan=fixture.plan(task)
        self.assertEqual(plan[0]["path"],"fixture/a.py")
        evidence=fixture.verify(
            task=task,
            lease=MutationLease("lease-1",task.task_id,"worker:impl",1,task.target_paths),
            change={"path":"fixture/a.py","patch":"+safe"},
            test_refs=("test:focused",),
            review_refs=("review:independent",),
            implementer_id="worker:impl",
            verifier_id="worker:verify",
        )
        self.assertEqual(evidence.rollback_ref,"rollback:eng-1")
        self.assertEqual(evidence.verifier_id,"worker:verify")

    def test_self_verification_is_rejected(self):
        task=EngineeringTask("eng-1","bounded",("a",),hashlib.sha256(b"graph").hexdigest(),"rollback:x")
        with self.assertRaisesRegex(VerticalSuiteError,"independent"):
            EngineeringAgentFixture().verify(
                task=task,
                lease=MutationLease("lease","eng-1","same",1,("a",)),
                change={"x":1},
                test_refs=("test:1",),
                review_refs=("review:1",),
                implementer_id="same",
                verifier_id="same",
            )

if __name__=="__main__": unittest.main()
