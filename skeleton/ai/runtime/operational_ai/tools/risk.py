"""Default-deny classification of tool consequences before any executor call."""
from __future__ import annotations
from dataclasses import dataclass
from ..authority.canonical import ContractViolation,digest
from ..authority.grants import ToolGrant
from ..authority.identity import Actor
from .catalog import ToolDefinition


@dataclass(frozen=True,slots=True)
class Decision:
    allowed:bool
    risk:str
    reason:str
    contract_sha256:str


def preflight(definition:ToolDefinition,actor:Actor,session:str,
              grant:ToolGrant|None,*,now_ns:int,allow_effects:bool=False)->Decision:
    contract_digest=digest({"tool":definition.name,"version":definition.version,
                            "risk":definition.risk,"schema":definition.argument_schema})
    if grant is None:
        return Decision(False,definition.risk,"no-explicit-operator-grant",contract_digest)
    try:
        grant.check(tenant=actor.tenant,user=actor.user,session=session,
                    tool=definition.name,now_monotonic_ns=now_ns,
                    write=definition.risk!="readonly")
    except ContractViolation:
        return Decision(False,definition.risk,"scope-or-expiry-denied",contract_digest)
    if definition.risk!="readonly" and not allow_effects:
        return Decision(False,definition.risk,"effects-have-no-reconciliation-contract",contract_digest)
    return Decision(True,definition.risk,"explicit-policy-admitted",contract_digest)
