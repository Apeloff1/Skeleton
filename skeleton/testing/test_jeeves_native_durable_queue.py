"""Real SQLite/WAL durable native work-order tests with SYNTHETIC generator.

Only the backend's generated token stream is simulated. Native execution
reservation, authoritative replay, transaction custody, claim isolation,
cross-process reopen and receipt verification use production components.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import os
from pathlib import Path
import tempfile
import unittest

from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.contracts import (
    Identity, SpineLimits, Busy,
)
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.database import SpineDatabase
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.lease import SessionGate
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.coordinator import ExecutionSpine
from skeleton.ai.runtime.operational_ai.orchestration.execution_spine.supervisor import SupervisedAI
from skeleton.jeeves.native_fabric.contracts import Scope
from skeleton.jeeves.native_fabric.durable_queue import (
    DurableQueueHold, WorkOrder, WorkClaim, DurableNativeQueue,
)
from skeleton.testing.test_jeeves_native_sqlite_integration import (
    MODEL,TOKENIZER,SyntheticallyGenerated,
)


@unittest.skipUnless(os.name=="posix" and Path("/proc/self/fd").is_dir(),
                     "real protected SQLite requires Linux")
class TestNativeDurableWorkOrders(unittest.TestCase):
    PROMPT="Private prompt bound to a durable queue request"
    SESSION="work_order_session"
    REQUEST="work_order_request"

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=None
        self.gate=None
        self._open()
        self.addCleanup(self._close)
        self.scope=Scope("local","operator",MODEL,TOKENIZER)
        self.queue=DurableNativeQueue(
            self.worker,scope_sha256=self.scope.binding,
            clock_ns=lambda:1000000,
        )

    def _close(self):
        if self.gate is not None:
            self.gate.close()
            self.gate=None
        if self.db is not None:
            self.db.close()
            self.db=None

    def _open(self,*,subject="operator",backend=None):
        self.db=SpineDatabase(self.tmp.name)
        self.gate=SessionGate(self.tmp.name)
        self.backend=backend or SyntheticallyGenerated()
        self.spine=ExecutionSpine(
            db=self.db,session_gate=self.gate,
            identity=Identity("local",subject,MODEL,TOKENIZER),
            backend=self.backend,
            limits=SpineLimits(
                input_bytes=32768,response_bytes=131072,
                max_output_tokens=128,context_tokens=4096,
            ),
        )
        self.worker=SupervisedAI(self.spine)

    def _cold(self,*,subject="operator",backend=None):
        self._close()
        self._open(subject=subject,backend=backend)
        self.queue=DurableNativeQueue(
            self.worker,scope_sha256=self.scope.binding,
            clock_ns=lambda:1000000,
        )

    def _order(self,*,order_id="order_one",session=None,request=None,
               prompt=None,seed=0,priority=5,expires_ns=10000000):
        return WorkOrder(
            order_id,self.scope.binding,"local","operator",MODEL,TOKENIZER,
            session or self.SESSION,request or self.REQUEST,
            sha256((self.PROMPT if prompt is None else prompt).encode()).hexdigest(),
            seed,0.8,"operator",priority,1000000,expires_ns,
        )

    def _create(self,**kwargs):
        order=self._order(**kwargs)
        self.spine.create(order.session_id)
        self.queue.submit(order)
        return order

    def test_submit_persists_only_prompt_digest(self):
        order=self._create()
        status=self.queue.inspect(order.order_id)
        self.assertEqual(status["state"],"queued")
        self.assertNotIn(self.PROMPT,str(status))
        with self.db.snapshot() as conn:
            schema=conn.execute(
                "SELECT sql FROM sqlite_master WHERE name='jeeves_native_work_orders'"
            ).fetchone()[0]
            self.assertNotIn("prompt_text",schema)

    def test_claim_persists_nonrequeueable_owner_lease(self):
        order=self._create()
        claimed=self.queue.claim(order.order_id)
        self.assertEqual(self.queue.inspect(order.order_id)["state"],"claimed")
        with self.assertRaises(DurableQueueHold):
            self.queue.claim(order.order_id)
        self.assertFalse(self.queue.next_ready())
        self.assertEqual(self.backend.calls,0)

    def test_successful_native_turn_requires_committed_replay(self):
        order=self._create()
        claim=self.queue.claim(order.order_id)
        status=self.queue.execute_claimed(
            claim,prompt=self.PROMPT,operator_approved=True,
        )
        self.assertEqual(status["state"],"committed")
        self.assertEqual(self.backend.calls,1)
        self.assertEqual(status["native_output_sha256"],
                         sha256(self.backend.answer.encode()).hexdigest())
        self.assertEqual(self.queue.no_autoretry_status()["counts"]["committed"],1)

    def test_reconciliation_without_native_receipt_stays_claimed(self):
        order=self._create()
        claim=self.queue.claim(order.order_id)
        with self.assertRaises(DurableQueueHold):
            self.queue.reconcile(claim,prompt=self.PROMPT)
        self.assertEqual(self.backend.calls,0)
        self.assertEqual(self.queue.inspect(order.order_id)["state"],"claimed")

    def test_uncertain_backend_exception_never_requeues(self):
        bad=SyntheticallyGenerated(post_reservation_failure=True)
        self._cold(backend=bad)
        order=self._create()
        claim=self.queue.claim(order.order_id)
        with self.assertRaises(RuntimeError):
            self.queue.execute_claimed(
                claim,prompt=self.PROMPT,operator_approved=True,
            )
        self.assertEqual(bad.calls,1)
        self.assertEqual(self.queue.inspect(order.order_id)["state"],"claimed")
        self._cold()
        self.assertEqual(self.queue.inspect(order.order_id)["state"],"claimed")
        with self.assertRaises(DurableQueueHold):
            self.queue.claim(order.order_id)
        with self.assertRaises(DurableQueueHold):
            self.queue.reconcile(claim,prompt=self.PROMPT)
        self.assertEqual(self.backend.calls,0)

    def test_authoritative_turn_before_queue_commit_can_be_reconciled(self):
        order=self._create()
        claim=self.queue.claim(order.order_id)
        self.worker.turn(order.session_id,order.request_id,self.PROMPT,
                         seed=order.seed,temperature=order.temperature)
        self.assertEqual(self.backend.calls,1)
        self._cold()
        accepted=self.queue.reconcile(claim,prompt=self.PROMPT)
        self.assertEqual(accepted["state"],"committed")
        self.assertEqual(self.backend.calls,0)

    def test_orphan_claim_cold_recovery_without_volatile_token(self):
        order=self._create()
        self.queue.claim(order.order_id)
        self.worker.turn(order.session_id,order.request_id,self.PROMPT,
                         seed=order.seed,temperature=order.temperature)
        self._cold()
        recovered=self.queue.reconcile_orphaned(
            order.order_id,prompt=self.PROMPT,operator_approved=True,
        )
        self.assertEqual(recovered["state"],"committed")
        self.assertEqual(self.backend.calls,0)

    def test_orphan_without_committed_receipt_stays_held(self):
        order=self._create()
        self.queue.claim(order.order_id)
        self._cold()
        with self.assertRaises(DurableQueueHold):
            self.queue.reconcile_orphaned(
                order.order_id,prompt=self.PROMPT,operator_approved=True,
            )
        self.assertEqual(self.queue.inspect(order.order_id)["state"],"claimed")
        self.assertEqual(self.backend.calls,0)

    def test_orphan_operator_approval_required_without_native_call(self):
        order=self._create()
        self.queue.claim(order.order_id)
        with self.assertRaises(DurableQueueHold):
            self.queue.reconcile_orphaned(
                order.order_id,prompt=self.PROMPT,operator_approved=False,
            )
        self.assertEqual(self.backend.calls,0)

    def test_orphan_recovery_cannot_use_changed_prompt(self):
        order=self._create()
        self.queue.claim(order.order_id)
        self.worker.turn(order.session_id,order.request_id,self.PROMPT,
                         seed=order.seed,temperature=order.temperature)
        self._cold()
        with self.assertRaises(DurableQueueHold):
            self.queue.reconcile_orphaned(
                order.order_id,prompt="different",operator_approved=True,
            )
        self.assertEqual(self.backend.calls,0)

    def test_orphan_recovery_cannot_target_foreign_subject(self):
        order=self._create()
        self.queue.claim(order.order_id)
        self.worker.turn(order.session_id,order.request_id,self.PROMPT,
                         seed=order.seed,temperature=order.temperature)
        self._cold(subject="foreign")
        with self.assertRaises(DurableQueueHold):
            self.queue.reconcile_orphaned(
                order.order_id,prompt=self.PROMPT,operator_approved=True,
            )
        self.assertEqual(self.backend.calls,0)

    def test_held_completed_turn_requires_explicit_approval(self):
        order=self._create()
        claim=self.queue.claim(order.order_id)
        self.worker.turn(order.session_id,order.request_id,self.PROMPT,
                         seed=order.seed,temperature=order.temperature)
        self.queue.quarantine(claim)
        with self.assertRaises(DurableQueueHold):
            self.queue.reconcile(claim,prompt=self.PROMPT)
        accepted=self.queue.reconcile(
            claim,prompt=self.PROMPT,operator_approved=True,
        )
        self.assertEqual(accepted["state"],"committed")
        self.assertEqual(self.backend.calls,1)

    def test_held_uncommitted_turn_stays_held(self):
        order=self._create()
        claim=self.queue.claim(order.order_id)
        self.queue.quarantine(claim)
        with self.assertRaises(DurableQueueHold):
            self.queue.reconcile(
                claim,prompt=self.PROMPT,operator_approved=True,
            )
        self.assertEqual(self.queue.inspect(order.order_id)["state"],"held")
        self.assertEqual(self.backend.calls,0)

    def test_cancel_only_before_native_claim(self):
        order=self._create()
        self.queue.cancel_queued(order.order_id)
        self.assertEqual(self.queue.inspect(order.order_id)["state"],"cancelled")
        with self.assertRaises(DurableQueueHold):
            self.queue.claim(order.order_id)

    def test_cannot_cancel_claimed_native_request(self):
        order=self._create()
        self.queue.claim(order.order_id)
        with self.assertRaises(DurableQueueHold):
            self.queue.cancel_queued(order.order_id)

    def test_changed_prompt_never_enters_native_backend(self):
        order=self._create()
        claim=self.queue.claim(order.order_id)
        with self.assertRaises(DurableQueueHold):
            self.queue.execute_claimed(
                claim,prompt="different",
                operator_approved=True,
            )
        self.assertEqual(self.backend.calls,0)

    def test_missing_explicit_approval_never_generates(self):
        order=self._create()
        claim=self.queue.claim(order.order_id)
        with self.assertRaises(DurableQueueHold):
            self.queue.execute_claimed(
                claim,prompt=self.PROMPT,operator_approved=False,
            )
        self.assertEqual(self.backend.calls,0)

    def test_invalid_claim_token_does_not_unlock_native_execution(self):
        order=self._create()
        claim=self.queue.claim(order.order_id)
        forged=replace(claim,token="f"*64)
        with self.assertRaises(DurableQueueHold):
            self.queue.execute_claimed(
                forged,prompt=self.PROMPT,operator_approved=True,
            )
        self.assertEqual(self.backend.calls,0)

    def test_foreign_subject_cannot_read_or_reconcile(self):
        order=self._create()
        claim=self.queue.claim(order.order_id)
        self._cold(subject="foreign")
        with self.assertRaises(DurableQueueHold):
            self.queue.inspect(order.order_id)
        with self.assertRaises(DurableQueueHold):
            self.queue.reconcile(claim,prompt=self.PROMPT)

    def test_duplicate_session_request_different_order_denied(self):
        self._create()
        with self.assertRaises(Exception):
            self.queue.submit(self._order(order_id="other_order"))
        self.assertEqual(len(self.queue.inventory()),1)

    def test_inventory_is_bounded_to_owner(self):
        self._create()
        self.assertEqual(len(self.queue.inventory()),1)
        self.assertNotIn("claim_sha256",str(self.queue.inventory()))

    def test_durable_work_spec_tamper_refused(self):
        order=self._create()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_work_orders SET priority=priority+1",
            )
        with self.assertRaises(DurableQueueHold):
            self.queue.inspect(order.order_id)

    def test_durable_work_spec_hash_tamper_refused(self):
        order=self._create()
        with self.db.transaction() as conn:
            conn.execute(
                "UPDATE jeeves_native_work_orders SET spec_sha256=?",
                ("f"*64,),
            )
        with self.assertRaises(DurableQueueHold):
            self.queue.inspect(order.order_id)

    def test_claimed_state_survives_cold_reopen(self):
        order=self._create()
        claim=self.queue.claim(order.order_id)
        self._cold()
        self.assertEqual(self.queue.inspect(order.order_id)["state"],"claimed")
        self.assertFalse(self.queue.next_ready())
        with self.assertRaises(DurableQueueHold):
            self.queue.claim(order.order_id)

    def test_next_ready_priority_and_expiration(self):
        self._create(order_id="low",session="s_low",request="r_low",priority=1)
        self._create(order_id="high",session="s_high",request="r_high",priority=9)
        self.assertEqual(self.queue.next_ready(),("high","low"))

    def test_output_digest_tamper_refused_on_reconciliation(self):
        order=self._create()
        claim=self.queue.claim(order.order_id)
        self.worker.turn(order.session_id,order.request_id,self.PROMPT,
                         seed=order.seed,temperature=order.temperature)
        with self.db.transaction() as conn:
            conn.execute("UPDATE turns SET response=?", (b"tampered",))
        with self.assertRaises(Exception):
            self.queue.reconcile(claim,prompt=self.PROMPT)

    def test_native_receipt_cannot_be_reconciled_twice(self):
        order=self._create()
        claim=self.queue.claim(order.order_id)
        self.queue.execute_claimed(
            claim,prompt=self.PROMPT,operator_approved=True,
        )
        with self.assertRaises(DurableQueueHold):
            self.queue.reconcile(claim,prompt=self.PROMPT)
        self.assertEqual(self.backend.calls,1)

    def test_principal_bound_queue_inventory_ceiling(self):
        self.queue=DurableNativeQueue(
            self.worker,scope_sha256=self.scope.binding,
            maximum_orders=1,clock_ns=lambda:1000000,
        )
        self._create()
        self.spine.create("another_session")
        with self.assertRaises(DurableQueueHold):
            self.queue.submit(self._order(
                order_id="another",session="another_session",request="r_two",
            ))

    def test_preclaim_expiry_does_not_start_native_work(self):
        expired=self._order(expires_ns=1000001)
        self.spine.create(expired.session_id)
        self.queue.submit(expired)
        self.queue.clock_ns=lambda:1000001
        with self.assertRaises(DurableQueueHold):
            self.queue.claim(expired.order_id)
        self.assertEqual(self.backend.calls,0)
        self.assertEqual(self.queue.inspect(expired.order_id)["state"],"queued")

    def test_authoritative_receipt_after_failed_generation_remains_pending(self):
        bad=SyntheticallyGenerated(post_reservation_failure=True)
        self._cold(backend=bad)
        order=self._create()
        claim=self.queue.claim(order.order_id)
        with self.assertRaises(RuntimeError):
            self.queue.execute_claimed(
                claim,prompt=self.PROMPT,operator_approved=True,
            )
        self.assertEqual(bad.calls,1)
        with self.db.snapshot() as conn:
            self.assertEqual(
                conn.execute("SELECT state FROM requests").fetchone(),("pending",),
            )
        self.assertFalse(self.queue.next_ready())


if __name__=="__main__":
    unittest.main()
