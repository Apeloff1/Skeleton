"""Offline lifecycle source proof and exact-head gate non-promotion tests."""
import unittest
from skeleton.ai.runtime.operational_ai.offline_cognition.core.contracts import Scope,CognitionError
from skeleton.ai.runtime.operational_ai.offline_cognition.core.lifecycle_guard import (
    REQUIRED_CHECKS,CheckEvidence,release_report,proposed_ack,
    inspect_local_hash_journal,inspect_boot_sequence,
)
from skeleton.ai.runtime.operational_ai.offline_cognition.core.audit import Audit
from skeleton.ai.runtime.operational_ai.laptop_runtime.boot_chain import BootChain
S=Scope("local","owner","a"*64,"b"*64)
HEAD="c"*64

def all_checks(conclusion="success",head=HEAD):
    return tuple(CheckEvidence(workflow,head,conclusion,i+1)
                 for i,workflow in enumerate(REQUIRED_CHECKS))

def report(checks):
    return release_report(commit_sha256=HEAD,checks=checks,
            model_rights_observed=True,native_inference_observed=True,
            laptop_device_observed=True,clean_install_observed=True,
            independent_review_observed=True)

class LifecycleGuardTests(unittest.TestCase):
    def test_all_declared_greens_still_require_external_certification(self):
        result=report(all_checks())
        self.assertTrue(result["all_declared_checks_success"])
        self.assertFalse(result["external_exact_head_source_proved"])
        self.assertFalse(result["release_certified"])
        self.assertFalse(result["safe_to_merge_automatically"])

    def test_one_skipped_gate_is_held(self):
        entries=list(all_checks())
        entries[1]=CheckEvidence(REQUIRED_CHECKS[1],HEAD,"skipped",2)
        self.assertIn(REQUIRED_CHECKS[1]+":skipped",report(tuple(entries))["issues"])

    def test_superseded_exact_head_refused(self):
        with self.assertRaises(CognitionError):
            report(all_checks(head="d"*64))

    def test_missing_required_check_refused(self):
        with self.assertRaises(CognitionError):
            report(all_checks()[:-1])

    def test_duplicate_required_gate_refused(self):
        with self.assertRaises(CognitionError):
            report((all_checks()[0],)*len(REQUIRED_CHECKS))

    def test_unknown_gate_refused(self):
        with self.assertRaises(CognitionError):
            CheckEvidence("Untrusted Gate",HEAD,"success",1)

    def test_prevent_self_certified_model_rights(self):
        data=release_report(commit_sha256=HEAD,checks=all_checks(),
            model_rights_observed=False,native_inference_observed=True,
            laptop_device_observed=True,clean_install_observed=True,
            independent_review_observed=True)
        self.assertIn("model-rights",data["issues"])

    def test_outbox_proposal_never_acks(self):
        result=proposed_ack(S,event_key="evt_1",event_sha256="e"*64,
                            request_id="req_1")
        self.assertFalse(result["acknowledged"])
        self.assertFalse(result["operator_signature_verified"])

    def test_audit_chain_verification_is_process_local_only(self):
        audit=Audit("local")
        audit.record("created",{"sha":"a"*64})
        audit.record("replayed",{"sha":"b"*64})
        result=inspect_local_hash_journal(audit)
        self.assertEqual(result["count"],2)
        self.assertFalse(result["durable_sqlite_integrity_proved"])

    def test_boot_chain_incomplete_is_not_native_proof(self):
        chain=BootChain()
        chain.add("source-reviewed","1"*64)
        result=inspect_boot_sequence(chain)
        self.assertFalse(result["all_stages_present"])
        self.assertFalse(result["source_bytes_validated_by_this_function"])

    def test_refuse_arbitrary_boot_chain_object(self):
        with self.assertRaises(CognitionError):
            inspect_boot_sequence({"source-reviewed":"1"*64})

    def test_release_receipt_digest_is_deterministic(self):
        self.assertEqual(report(all_checks())["evidence_sha256"],
                         report(all_checks())["evidence_sha256"])

if __name__=="__main__":
    unittest.main()
