"""Deterministic bounded training execution state with crash-safe checkpoints."""
from __future__ import annotations
from dataclasses import dataclass, field
from hashlib import sha256
import hmac, json, math
from types import MappingProxyType
from typing import Any, Mapping

MAX_STEPS=10_000_000
MAX_CHECKPOINTS=1024
MAX_METRICS=128
MAX_METADATA_KEYS=128

class TrainingError(ValueError): pass
class BudgetExceeded(TrainingError): pass
class ReplayError(TrainingError): pass
class StateConflict(TrainingError): pass

def _plain(v):
    if isinstance(v,Mapping): return {str(k):_plain(x) for k,x in sorted(v.items(),key=lambda p:str(p[0]))}
    if isinstance(v,tuple): return [_plain(x) for x in v]
    return v

def _freeze(v):
    if v is None or isinstance(v,(str,bool,int)): return v
    if isinstance(v,float):
        if not math.isfinite(v): raise TrainingError("non-finite value")
        return v
    if isinstance(v,Mapping):
        if len(v)>MAX_METADATA_KEYS: raise TrainingError("mapping too large")
        return MappingProxyType({str(k):_freeze(x) for k,x in sorted(v.items(),key=lambda p:str(p[0]))})
    if isinstance(v,(list,tuple)):
        if len(v)>MAX_METADATA_KEYS: raise TrainingError("sequence too large")
        return tuple(_freeze(x) for x in v)
    raise TrainingError("value must be canonical JSON")

def _digest(v):
    return sha256(json.dumps(_plain(v),sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def _hex(v,name):
    if not isinstance(v,str) or len(v)!=64:
        raise TrainingError(f"invalid {name}")
    try: int(v,16)
    except ValueError as exc: raise TrainingError(f"invalid {name}") from exc
    if v.lower()!=v: raise TrainingError(f"invalid {name}")
    return v

@dataclass(frozen=True)
class TrainingBudget:
    max_steps:int
    max_tokens:int
    max_compute_units:int
    max_checkpoints:int=128
    def __post_init__(self):
        for name in ("max_steps","max_tokens","max_compute_units","max_checkpoints"):
            v=getattr(self,name)
            if not isinstance(v,int) or isinstance(v,bool) or v<=0: raise TrainingError(f"invalid {name}")
        if self.max_steps>MAX_STEPS or self.max_checkpoints>MAX_CHECKPOINTS: raise TrainingError("budget exceeds hard bound")

@dataclass(frozen=True)
class StepReceipt:
    run_digest:str; ordinal:int; input_digest:str; output_digest:str
    tokens:int; compute_units:int; metrics:Mapping[str,float]=field(default_factory=dict)
    def __post_init__(self):
        _hex(self.run_digest,"run_digest"); _hex(self.input_digest,"input_digest"); _hex(self.output_digest,"output_digest")
        if not isinstance(self.ordinal,int) or isinstance(self.ordinal,bool) or self.ordinal<1 or self.ordinal>MAX_STEPS: raise TrainingError("invalid ordinal")
        for name in ("tokens","compute_units"):
            v=getattr(self,name)
            if not isinstance(v,int) or isinstance(v,bool) or v<0: raise TrainingError(f"invalid {name}")
        if len(self.metrics)>MAX_METRICS: raise TrainingError("too many metrics")
        clean={}
        for k,v in sorted(self.metrics.items()):
            if not isinstance(k,str) or not k or len(k)>128: raise TrainingError("invalid metric name")
            if not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v): raise TrainingError("invalid metric value")
            clean[k]=float(v)
        object.__setattr__(self,"metrics",MappingProxyType(clean))
    def to_dict(self):
        return {"run_digest":self.run_digest,"ordinal":self.ordinal,"input_digest":self.input_digest,"output_digest":self.output_digest,"tokens":self.tokens,"compute_units":self.compute_units,"metrics":dict(self.metrics)}
    @property
    def receipt_digest(self): return _digest(self.to_dict())

@dataclass(frozen=True)
class TrainingCheckpoint:
    run_digest:str; ordinal:int; prior_checkpoint_digest:str|None
    state_digest:str; cumulative_tokens:int; cumulative_compute_units:int
    receipt_digests:tuple[str,...]
    def __post_init__(self):
        _hex(self.run_digest,"run_digest"); _hex(self.state_digest,"state_digest")
        if self.prior_checkpoint_digest is not None: _hex(self.prior_checkpoint_digest,"prior_checkpoint_digest")
        if not isinstance(self.ordinal,int) or isinstance(self.ordinal,bool) or self.ordinal<0: raise TrainingError("invalid checkpoint ordinal")
        for name in ("cumulative_tokens","cumulative_compute_units"):
            v=getattr(self,name)
            if not isinstance(v,int) or isinstance(v,bool) or v<0: raise TrainingError(f"invalid {name}")
        if len(self.receipt_digests)>MAX_STEPS: raise TrainingError("receipt chain too large")
        object.__setattr__(self,"receipt_digests",tuple(_hex(x,"receipt_digest") for x in self.receipt_digests))
    def to_dict(self):
        return {"run_digest":self.run_digest,"ordinal":self.ordinal,"prior_checkpoint_digest":self.prior_checkpoint_digest,"state_digest":self.state_digest,"cumulative_tokens":self.cumulative_tokens,"cumulative_compute_units":self.cumulative_compute_units,"receipt_digests":list(self.receipt_digests)}
    @property
    def checkpoint_digest(self): return _digest(self.to_dict())

class TrainingExecution:
    """Pure state machine: callers perform compute; this object verifies and accounts it."""
    def __init__(self,run_digest:str,budget:TrainingBudget,seed:int):
        self.run_digest=_hex(run_digest,"run_digest")
        if not isinstance(budget,TrainingBudget): raise TrainingError("TrainingBudget required")
        if not isinstance(seed,int) or isinstance(seed,bool): raise TrainingError("seed must be integer")
        self.budget=budget; self.seed=seed; self._receipts=[]; self._checkpoints=[]; self._closed=False
    @property
    def next_ordinal(self): return len(self._receipts)+1
    @property
    def totals(self): return (sum(x.tokens for x in self._receipts),sum(x.compute_units for x in self._receipts))
    @property
    def state_digest(self):
        return _digest({"run_digest":self.run_digest,"seed":self.seed,"budget":self.budget.__dict__,"receipts":[r.receipt_digest for r in self._receipts],"closed":self._closed})
    def record_step(self,receipt:StepReceipt):
        if self._closed: raise StateConflict("execution closed")
        if not isinstance(receipt,StepReceipt) or receipt.run_digest!=self.run_digest: raise ReplayError("receipt run mismatch")
        if receipt.ordinal!=self.next_ordinal: raise ReplayError("non-contiguous receipt")
        steps=self.next_ordinal; tokens,compute=self.totals
        if steps>self.budget.max_steps or tokens+receipt.tokens>self.budget.max_tokens or compute+receipt.compute_units>self.budget.max_compute_units:
            raise BudgetExceeded("training budget exceeded")
        self._receipts.append(receipt); return receipt.receipt_digest
    def checkpoint(self):
        if self._closed: raise StateConflict("execution closed")
        if len(self._checkpoints)>=self.budget.max_checkpoints: raise BudgetExceeded("checkpoint budget exceeded")
        tokens,compute=self.totals
        cp=TrainingCheckpoint(self.run_digest,len(self._receipts),self._checkpoints[-1].checkpoint_digest if self._checkpoints else None,self.state_digest,tokens,compute,tuple(r.receipt_digest for r in self._receipts))
        self._checkpoints.append(cp); return cp
    def recover(self,checkpoint:TrainingCheckpoint,receipts:tuple[StepReceipt,...]):
        if self._receipts or self._checkpoints or self._closed: raise StateConflict("recovery requires fresh execution")
        if not isinstance(checkpoint,TrainingCheckpoint) or checkpoint.run_digest!=self.run_digest: raise ReplayError("checkpoint run mismatch")
        if len(receipts)!=checkpoint.ordinal or tuple(r.receipt_digest for r in receipts)!=checkpoint.receipt_digests: raise ReplayError("checkpoint receipt chain mismatch")
        for r in receipts: self.record_step(r)
        tokens,compute=self.totals
        if (tokens,compute)!=(checkpoint.cumulative_tokens,checkpoint.cumulative_compute_units): raise ReplayError("checkpoint accounting mismatch")
        if not hmac.compare_digest(self.state_digest,checkpoint.state_digest): raise ReplayError("checkpoint state mismatch")
        self._checkpoints.append(checkpoint); return self.state_digest
    def close(self):
        if self._closed: raise StateConflict("execution already closed")
        self._closed=True
        return _digest({"run_digest":self.run_digest,"final_state_digest":self.state_digest,"receipt_digests":[r.receipt_digest for r in self._receipts],"authority_scope":"research-only"})
