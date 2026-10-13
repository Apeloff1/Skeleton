"""Real shell approval lease boundaries, not command execution.

Approval receipts must be exact SHA-256 fingerprints, scoped to one
principal/intent/proposal, expired after their lease, and consumed exactly
once even under concurrent review.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import unittest

from skeleton.ai.shell.approval import AIApprovalError, AIApprovalRegistry


class ShellApprovalContractTests(unittest.TestCase):
    def setUp(self):
        self.now=[100.0]
        self.registry=AIApprovalRegistry(
            max_approvals=10,clock=lambda: self.now[0])
        self.values={
            "principal":"worker_alpha",
            "intent_fingerprint":"a"*64,
            "proposal_fingerprint":"b"*64,
            "approved_by":"human_reviewer",
        }

    def approve(self,**overrides):
        return self.registry.approve(**{**self.values,**overrides})

    def use(self,receipt,action="require",**overrides):
        fields={k:self.values[k] for k in (
            "principal","intent_fingerprint","proposal_fingerprint")}
        return getattr(self.registry,action)(receipt,**{**fields,**overrides})

    def test_exact_receipt_authorizes_same_intent_only(self):
        approval=self.approve(ttl_seconds=5.0)
        self.assertEqual(self.use(approval).approval_id,approval.approval_id)
        self.assertEqual(approval.principal,"worker_alpha")
        self.assertFalse(approval.consumed)
        for fields in (
            {"principal":"worker_beta"},
            {"intent_fingerprint":"c"*64},
            {"proposal_fingerprint":"d"*64},
        ):
            with self.subTest(fields=fields),self.assertRaises(AIApprovalError):
                self.use(approval,**fields)
        self.assertEqual(self.use(approval,"consume").approval_id,
                         approval.approval_id)
        with self.assertRaises(AIApprovalError):
            self.use(approval)
        with self.assertRaises(AIApprovalError):
            self.use(approval,"consume")

    def test_exact_lease_expiry_and_clock_rollback_guard(self):
        approval=self.approve(ttl_seconds=2.0)
        self.now[0]=101.99
        self.use(approval)
        self.now[0]=102.0
        with self.assertRaises(AIApprovalError):
            self.use(approval)

    def test_nonhex_or_nonstring_fingerprints_cannot_be_approved(self):
        for invalid in ("x"*64,"A"*64,"a"*63,True,0,None,object()):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                self.approve(intent_fingerprint=invalid)
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                self.approve(proposal_fingerprint=invalid)

    def test_ttl_nan_inf_boolean_and_invalid_clock_refused(self):
        for invalid in (0,-1,True,float("nan"),float("inf"),-float("inf"),"2"):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                self.approve(ttl_seconds=invalid)
        approval=self.approve()
        for invalid in (True,"now",float("nan"),float("inf")):
            self.now[0]=invalid
            with self.subTest(invalid=invalid),self.assertRaises(AIApprovalError):
                self.use(approval)

    def test_capacity_refused_and_consumed_receipts_free_capacity(self):
        clock=[0.0]
        registry=AIApprovalRegistry(max_approvals=1,clock=lambda:clock[0])
        item=registry.approve(**self.values)
        with self.assertRaises(AIApprovalError):
            registry.approve(**self.values)
        registry.consume(item,principal=self.values["principal"],
                        intent_fingerprint=self.values["intent_fingerprint"],
                        proposal_fingerprint=self.values["proposal_fingerprint"])
        next_item=registry.approve(**self.values)
        self.assertNotEqual(item.approval_id,next_item.approval_id)
        with self.assertRaises(ValueError):
            AIApprovalRegistry(max_approvals=True)

    def test_racing_consumers_get_one_success_no_replay(self):
        receipt=self.approve()
        def consume(_):
            try:
                self.use(receipt,"consume")
                return True
            except AIApprovalError:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(consume,range(32)))
        self.assertEqual(sum(results),1)
        with self.assertRaises(AIApprovalError):
            self.use(receipt)


if __name__ == "__main__":
    unittest.main()
