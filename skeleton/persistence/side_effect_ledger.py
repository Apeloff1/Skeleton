from dataclasses import dataclass
@dataclass(frozen=True)
class SideEffect: effect_id:str; operation:str; idempotency_key:str
@dataclass(frozen=True)
class EffectAttempt: effect:SideEffect; attempt:int; state:str
@dataclass(frozen=True)
class EffectReceipt: attempt:EffectAttempt; outcome:str
def begin(effect,prior=()):
 if not effect.idempotency_key:raise ValueError("idempotency key required")
 if any(x.effect.idempotency_key==effect.idempotency_key and x.state in {"pending","succeeded","unknown"} for x in prior):raise PermissionError("effect already active/resolved/unknown")
 return EffectAttempt(effect,len(tuple(prior))+1,"pending")
def receipt(a,outcome):
 if outcome not in {"succeeded","failed","unknown"}:raise ValueError("invalid effect outcome")
 return EffectReceipt(a,outcome)
