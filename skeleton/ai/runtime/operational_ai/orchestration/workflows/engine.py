"""Workflow executor integrates a *real* gateway and deterministic safe steps.

Native model generation is supplied through ModelGateway. No mock, stale
cache, or provider response is ever invented in the product execution path.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any,Callable
import time
from .graph import WorkflowGraph,WorkflowError
from .cancel import Cancellation
from .budget import WorkflowLimits,WorkflowBudget
from .verify import verify_output
from .checkpoint import seal,Checkpoint

@dataclass(frozen=True,slots=True)
class WorkflowOutcome:
    status:str
    results:dict
    checkpoints:tuple[Checkpoint,...]
    spent:dict
    elapsed_ns:int

class WorkflowEngine:
    def __init__(self,graph:WorkflowGraph,handlers:dict[str,Callable[[dict],dict]],
                 *,limits:WorkflowLimits|None=None):
        self.graph=graph
        self.handlers=handlers
        self.limits=limits or WorkflowLimits()
        if any(s.kind not in handlers for s in graph.steps):
            raise WorkflowError('workflow handler missing for declared step')

    def run(self,workflow_id:str,initial:dict,*,cancel:Cancellation|None=None)->WorkflowOutcome:
        if not isinstance(workflow_id,str) or not workflow_id or len(workflow_id)>128:
            raise WorkflowError('invalid workflow ID')
        if not isinstance(initial,dict) or len(initial)>128:
            raise WorkflowError('invalid initial workflow state')
        started=time.monotonic_ns()
        token=cancel or Cancellation(started+self.limits.deadline_ms*1_000_000)
        budget=WorkflowBudget(self.limits)
        state=dict(initial);checkpoints=[]
        for step in self.graph.ordered():
            token.checkpoint()
            budget.spend(operations=1)
            if step.input_key not in state:raise WorkflowError('workflow input missing')
            arg=state[step.input_key]
            if step.kind=='infer':budget.spend(inference_calls=1)
            if step.kind=='tool-proposal':budget.spend(max_tool_calls=1)
            import json
            bytes_in=len(json.dumps(arg,allow_nan=False).encode())
            budget.spend(max_input_bytes=bytes_in)
            handler=self.handlers[step.kind]
            try:
                result=handler({'step':step.id,'value':arg,'scope':workflow_id,
                                'cancelled':token.cancelled})
            except Exception as exc:
                raise WorkflowError(f'workflow step {step.id} failed; no implicit side-effect retry') from exc
            if not isinstance(result,dict):raise WorkflowError('workflow handler returned non-object')
            byte_out=len(json.dumps(result,allow_nan=False).encode())
            budget.spend(max_output_bytes=byte_out)
            token.checkpoint()
            state[step.output_key]=result
            checkpoints.append(seal(workflow_id,step.id,{'value':arg},result))
        return WorkflowOutcome('completed',state,tuple(checkpoints),dict(budget.used),time.monotonic_ns()-started)
