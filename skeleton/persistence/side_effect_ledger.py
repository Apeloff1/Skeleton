from dataclasses import dataclass
_STATES=frozenset({"pending","succeeded","failed","unknown"})
@dataclass(frozen=True)
class SideEffect: effect_id:str; operation:str; idempotency_key:str
@dataclass(frozen=True)
class EffectAttempt:
 effect:SideEffect; attempt:int; state:str
 def __post_init__(self):
  if not self.effect.effect_id or not self.effect.operation or not self.effect.idempotency_key or isinstance(self.attempt,bool) or self.attempt<=0 or self.state not in _STATES:raise ValueError("invalid effect attempt")
@dataclass(frozen=True)
class EffectReceipt: attempt:EffectAttempt; outcome:str
def begin(effect,prior=()):
 prior=tuple(prior)
 if not effect.idempotency_key:raise ValueError("idempotency key required")
 same=[x for x in prior if x.effect.idempotency_key==effect.idempotency_key]
 if any(x.state in {"pending","succeeded","unknown"} for x in same):raise PermissionError("effect already active/resolved/unknown")
 return EffectAttempt(effect,(max((x.attempt for x in same),default=0)+1),"pending")
def receipt(a,outcome):
 if a.state!="pending" or outcome not in {"succeeded","failed","unknown"}:raise ValueError("invalid effect outcome")
 return EffectReceipt(EffectAttempt(a.effect,a.attempt,outcome),outcome)
