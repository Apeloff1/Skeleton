"""Promotion evidence is not invented from pending or unknown CI states."""
import unittest
from skeleton.ai.runtime.operational_ai.trust_gates import GateViolation
from skeleton.ai.runtime.operational_ai.trust_gates.applications.release_evidence import REQUIRED,qualify_record

class ReleaseEvidence(unittest.TestCase):
    def setUp(self):
        self.statuses={name:"success" for name in REQUIRED}
    def check(self,**changes):
        args={"head_sha":"a"*64,"observed":dict(self.statuses),"reviewed":True,
              "native_e2e":True,"rights_approved":True,"installation_proved":True}
        args.update(changes)
        return qualify_record(**args)
    def test_all_explicit_holds_required(self):
        self.assertEqual(self.check()["status"],"accepted")
    def test_unknown_and_missing_check_are_denied(self):
        old=dict(self.statuses);old.pop("Malware Gate")
        with self.assertRaises(GateViolation):self.check(observed=old)
    def test_no_non_success_substitute(self):
        for state in ("failure","pending","cancelled","skipped"):
            candidate=dict(self.statuses)
            candidate["Dependency Review"]=state
            with self.subTest(state=state):
                with self.assertRaises(GateViolation):self.check(observed=candidate)
    def test_independent_review_cannot_be_skipped(self):
        with self.assertRaises(GateViolation):self.check(reviewed=False)
    def test_native_model_e2e_cannot_be_skipped(self):
        with self.assertRaises(GateViolation):self.check(native_e2e=False)
    def test_installer_and_rights_are_separate(self):
        with self.assertRaises(GateViolation):self.check(installation_proved=False)
        with self.assertRaises(GateViolation):self.check(rights_approved=False)

if __name__=="__main__": unittest.main()
