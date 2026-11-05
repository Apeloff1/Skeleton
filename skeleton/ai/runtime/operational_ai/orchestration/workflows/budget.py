"""Per-workflow resource accounting with monotonic spend and no refund on failure."""
from __future__ import annotations
from dataclasses import dataclass
from .graph import WorkflowError

@dataclass(frozen=True,slots=True)
class WorkflowLimits:
    operations:int=16
    inference_calls:int=4
    max_input_bytes:int=128_000
    max_output_bytes:int=128_000
    max_tool_calls:int=0
    deadline_ms:int=120_000

    def __post_init__(self):
        for key,ceiling in [('operations',256),('inference_calls',16),('max_input_bytes',2_000_000),
                            ('max_output_bytes',2_000_000),('max_tool_calls',64),('deadline_ms',600_000)]:
            value=getattr(self,key)
            if type(value) is not int or not 0<=value<=ceiling:
                raise WorkflowError(f'invalid workflow budget: {key}')
        if self.operations<1 or self.inference_calls<1 or self.deadline_ms<1:
            raise WorkflowError('zero core execution budget')

class WorkflowBudget:
    def __init__(self,limits:WorkflowLimits):
        self.limits=limits
        self.used={name:0 for name in limits.__dataclass_fields__ if name!='deadline_ms'}

    def spend(self,**amounts:int)->None:
        for name,value in amounts.items():
            if name not in self.used or type(value) is not int or value<0:
                raise WorkflowError('invalid workflow resource charge')
            if self.used[name]+value>getattr(self.limits,name):
                raise WorkflowError(f'workflow {name} budget exceeded')
        for name,value in amounts.items():self.used[name]+=value
