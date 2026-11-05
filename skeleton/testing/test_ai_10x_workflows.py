"""Bounded DAG orchestration, stable snapshots, backpressure and deadline coverage."""
from __future__ import annotations
import time,unittest
from skeleton.ai.runtime.operational_ai.orchestration.workflows.graph import Step,WorkflowGraph,WorkflowError
from skeleton.ai.runtime.operational_ai.orchestration.workflows.planner import PlanCompiler
from skeleton.ai.runtime.operational_ai.orchestration.workflows.engine import WorkflowEngine
from skeleton.ai.runtime.operational_ai.orchestration.workflows.budget import WorkflowLimits
from skeleton.ai.runtime.operational_ai.orchestration.workflows.cancel import Cancellation
from skeleton.ai.runtime.operational_ai.orchestration.workflows.schedule import FairAdmissionQueue
from skeleton.ai.runtime.operational_ai.orchestration.workflows.checkpoint import verify

class TestWorkflows(unittest.TestCase):
    def test_dependency_graph_in_correct_order(self):
        graph=PlanCompiler().offline_chat()
        self.assertEqual([s.id for s in graph.ordered()],['ground','infer','verify','persist'])
        self.assertEqual(graph.critical_path(),4)

    def test_cycles_refused(self):
        with self.assertRaises(WorkflowError):
            WorkflowGraph((Step('a','infer',('b',),'text','result'),
                           Step('b','verify',('a',),'result','verified')))

    def test_execution_budgets_and_checkpoint(self):
        graph=PlanCompiler().offline_chat()
        handlers={kind:lambda x:{'text':str(x['value'])} for kind in ('context','infer','verify','persist')}
        out=WorkflowEngine(graph,handlers).run('workflow',{'question':'hello'})
        self.assertEqual(out.status,'completed')
        self.assertEqual(out.spent['operations'],4)
        self.assertEqual(len(out.checkpoints),4)
        self.assertTrue(verify(out.checkpoints[0],{'value':'hello'}))

    def test_inference_budget_blocks(self):
        graph=PlanCompiler().offline_chat()
        with self.assertRaises(WorkflowError):
            WorkflowEngine(graph,{k:lambda x:{} for k in ('context','infer','verify','persist')},
                           limits=WorkflowLimits(operations=2)).run('op',{'question':'hello'})

    def test_cancel_propagates(self):
        token=Cancellation(time.monotonic_ns()+10_000_000_000)
        child=token.child(budget_ms=100)
        token.cancel()
        with self.assertRaises(WorkflowError):child.checkpoint()

    def test_scheduler_fair_tenants(self):
        queue=FairAdmissionQueue(per_tenant=2)
        queue.enqueue('a','one');queue.enqueue('a','two');queue.enqueue('b','one')
        self.assertEqual([queue.pop().tenant for _ in range(3)],['a','b','a'])

    def test_scheduler_duplicate_denied(self):
        queue=FairAdmissionQueue();queue.enqueue('a','one')
        with self.assertRaises(WorkflowError):queue.enqueue('a','one')

if __name__=='__main__':unittest.main()
