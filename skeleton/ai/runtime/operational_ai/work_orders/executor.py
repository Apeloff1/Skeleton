"""Single real GGUF call guarded by a durable dispatch fence.

All success is confirmed by an independent READ-ONLY replay from the
authoritative ExecutionSpine. Caller-provided proof strings cannot commit.
"""
from __future__ import annotations
from .model import WorkOrder
from .store import WorkOrderStore
from .contracts import refuse
class WorkOrderExecutor:
    def __init__(self,store,worker):
        if not isinstance(store,WorkOrderStore) or worker is None or not callable(
                getattr(worker,"turn",None)) or not hasattr(worker,"spine"):
            refuse("durable queue and canonical native supervisor required")
        self.store=store;self.worker=worker

    def run(self,order,prompt_text,*,expected_revision=1):
        if not isinstance(order,WorkOrder):refuse("typed work order required")
        order.confirm_prompt(prompt_text);order.confirm_worker(self.worker)
        row=self.store.inspect(order)
        if row["status"]!="queued" or row["revision"]!=expected_revision:
            refuse("already executed or unknown effect must be reconciled")
        # Reserving the full configured context plus output is conservative.
        # The canonical native context/token admission does the exact count.
        limits=self.worker.spine.limits
        reserve=limits.context_tokens+order.max_output_tokens
        claimed=self.store.claim(order,expected_revision=expected_revision,
                                 reservation_tokens=reserve)
        self.store.dispatch(order,claimed["lease"],
                            expected_revision=claimed["revision"])
        # No exception handler releases or automatically repeats uncertain work.
        self.worker.turn(order.session_id,order.request_id,prompt_text,
                seed=order.seed,temperature=order.sampler_temperature)
        return self.store.reconcile(order,self.worker,prompt_text)

    def reconcile(self,order,prompt_text):
        if not isinstance(order,WorkOrder):refuse("typed work order required")
        return self.store.reconcile(order,self.worker,prompt_text)
