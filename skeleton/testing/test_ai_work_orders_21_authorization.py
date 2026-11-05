"""Operator HMAC tickets are bounded, scoped and cannot be forged from model text."""
import unittest
from skeleton.testing.work_orders_test_support import QueueCase
from skeleton.ai.runtime.operational_ai.work_orders.authorization import OperatorAuthority
from skeleton.ai.runtime.operational_ai.work_orders.ingress import SignedIngress
from skeleton.ai.runtime.operational_ai.work_orders.contracts import WorkOrderError

class AdmissionTests(QueueCase):
    def setUp(self):
        super().setUp()
        self.authority=OperatorAuthority(b"K"*32)
        self.ingress=SignedIngress(self.store,self.authority)
    def ticket(self):
        return self.authority.issue(self.order,issued_at=100,
                                    expires_at=200,approved=True)
    def test_signed_operator_job_and_nonce_single_use(self):
        token=self.ticket()
        admitted=self.ingress.submit(self.order,token,observed_at=150)
        self.assertTrue(admitted["nonce_consumed"])
        self.assertEqual(self.store.inspect(self.order)["status"],"queued")
        with self.assertRaises(WorkOrderError):
            self.ingress.submit(self.order,token,observed_at=150)
        self.assertEqual(self.store.audit()["jobs"],1)
    def test_tampered_ticket_fails_before_mutation(self):
        token=self.ticket()
        token["record"]["tenant"]="other"
        with self.assertRaises(WorkOrderError):
            self.ingress.submit(self.order,token,observed_at=150)
        self.assertEqual(self.store.list_jobs(tenant="local",subject="owner",
                                            model_sha256="a"*64),())
    def test_expired_token_cannot_admit(self):
        with self.assertRaises(WorkOrderError):
            self.ingress.submit(self.order,self.ticket(),observed_at=200)
    def test_model_or_request_identity_change_refused(self):
        with self.assertRaises(WorkOrderError):
            self.ingress.submit(self.other_order(prompt_text="different"),
                               self.ticket(),observed_at=150)
    def test_unapproved_operator_cannot_issue_ticket(self):
        with self.assertRaises(WorkOrderError):
            self.authority.issue(self.order,issued_at=100,
                                 expires_at=200,approved=False)
    def test_short_key_denied(self):
        with self.assertRaises(WorkOrderError):OperatorAuthority(b"short")
    def test_nonce_is_durable_across_restarts(self):
        token=self.ticket()
        self.ingress.submit(self.order,token,observed_at=150)
        self.store.close()
        from skeleton.ai.runtime.operational_ai.work_orders import WorkOrderStore
        self.store=WorkOrderStore(self.state_dir,clock=lambda:100000)
        new_ingress=SignedIngress(self.store,self.authority)
        with self.assertRaises(WorkOrderError):
            new_ingress.submit(self.order,token,observed_at=150)
