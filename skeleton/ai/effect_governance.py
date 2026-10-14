"""October-2026 fail-closed governance across tool health, effects and compensation."""
from dataclasses import dataclass
import hashlib, json
from skeleton.observability.tool_health import ToolHealth, authorize_risky
from skeleton.persistence.side_effect_ledger import SideEffect, EffectAttempt, begin
from skeleton.reliability.compensation import Compensation

@dataclass(frozen=True)
class EffectAuthorization:
 operation_id:str; effect_id:str; idempotency_key:str; health_probe_id:str; compensation_digest:str; authorization_digest:str

def _sha(x):
 return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def authorize_effect(operation_id:str,effect:SideEffect,health:ToolHealth,compensation:Compensation,*,now:int,max_health_age:int,prior:tuple[EffectAttempt,...]=()):
 if not operation_id or compensation.operation_id!=operation_id: raise PermissionError("operation/compensation authority mismatch")
 if not authorize_risky(health,now,max_health_age): raise PermissionError("tool health does not authorize side effect")
 if {s.effect_id for s in compensation.steps}!={effect.effect_id}: raise PermissionError("exact effect compensation required")
 attempt=begin(effect,prior)
 comp=_sha({"operation_id":compensation.operation_id,"steps":[(s.step_id,s.effect_id,s.action) for s in compensation.steps]})
 body={"operation_id":operation_id,"effect_id":effect.effect_id,"idempotency_key":effect.idempotency_key,"probe":health.probe.probe_id,"compensation":comp}
 return attempt,EffectAuthorization(operation_id,effect.effect_id,effect.idempotency_key,health.probe.probe_id,comp,_sha(body))
