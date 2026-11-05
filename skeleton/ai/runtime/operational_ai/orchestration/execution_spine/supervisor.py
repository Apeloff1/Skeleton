"""Accountable supervised execution. No provider fallback, invisible retries or mutation."""
from __future__ import annotations
import time
from .coordinator import ExecutionSpine
from .contracts import Conflict,SpineError,Busy,Cancelled
from .quota import Quota
from .circuit import RuntimeCircuit
from .metrics import Metrics

class SupervisedAI:
    def __init__(self,spine:ExecutionSpine,quota:Quota|None=None,
                 circuit:RuntimeCircuit|None=None,metrics:Metrics|None=None):
        self.spine=spine;self.quota=quota or Quota(max_active_total=4,max_per_principal=1)
        self.circuit=circuit or RuntimeCircuit();self.metrics=metrics or Metrics()
    def turn(self,*args,**kwargs):
        start=time.monotonic_ns()
        try:
            with self.quota.reserve(self.spine.identity):
                self.circuit.allow()
                response=self.spine.turn(*args,**kwargs)
            if response['replayed']:
                self.metrics.observe(outcome='replayed',duration_ns=time.monotonic_ns()-start)
            else:
                self.circuit.success()
                self.metrics.observe(outcome='ok',prompt_tokens=response['prompt_tokens'],
                    output_tokens=response['generated_tokens'],duration_ns=time.monotonic_ns()-start)
            return response
        except (Busy,Cancelled,Conflict):
            self.metrics.observe(outcome='held',duration_ns=time.monotonic_ns()-start)
            raise
        except BaseException:
            self.circuit.failure()
            self.metrics.observe(outcome='failed',duration_ns=time.monotonic_ns()-start)
            raise
    def status(self):
        return {'model_circuit':self.circuit.status(),
            'capacity':self.quota.snapshot(),
            'metrics':self.metrics.snapshot().__dict__ if hasattr(self.metrics.snapshot(),'__dict__') else
                {key:getattr(self.metrics.snapshot(),key) for key in self.metrics.snapshot().__dataclass_fields__}}
