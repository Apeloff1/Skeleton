"""Explicit, idempotent, policy-gated tool execution independent from model text."""
from __future__ import annotations
from dataclasses import dataclass
import time
from ..authority.budgets import BudgetLedger
from ..authority.canonical import ContractViolation,canonical_bytes,digest
from ..authority.grants import ToolGrant
from ..authority.identity import Actor,require_id
from ..persistence.journal import EventJournal
from ..persistence.intent import IntentLedger
from .catalog import ToolCatalog
from .schemas import validate
from .risk import preflight


@dataclass(frozen=True,slots=True)
class ToolReceipt:
    name:str
    invocation:str
    input_digest:str
    output_digest:str
    output:dict
    replayed:bool=False


class ToolExecutor:
    def __init__(self,catalog:ToolCatalog,journal:EventJournal):
        self.catalog=catalog
        self.journal=journal
        self.intents=IntentLedger(journal)

    def invoke(self,*,actor:Actor,session:str,invocation:str,name:str,
               args:dict,grant:ToolGrant,ledger:BudgetLedger)->ToolReceipt:
        require_id(session,field="tool session")
        require_id(invocation,field="invocation")
        definition,impl=self.catalog.resolve(name)
        validate(args,definition.argument_schema)
        decision=preflight(definition,actor,session,grant,
                           now_ns=time.monotonic_ns(),allow_effects=False)
        if not decision.allowed:
            raise ContractViolation(f"tool risk admission denied: {decision.reason}")
        signature=digest({"tool":name,"version":definition.version,"args":args,
                          "actor":actor.to_record(),"session":session})
        event_id=f"tool_{invocation}"
        prior=[e for e in self.journal.replay(session) if e.event_id==event_id]
        if prior:
            data=prior[0].payload
            if data.get("input_digest")!=signature:
                raise ContractViolation("idempotency key reused with new tool arguments")
            return ToolReceipt(name,invocation,signature,data["output_digest"],data["output"],True)
        ledger.charge(tool_calls=1)
        # Only readonly handlers are presently wired. Side-effecting adapters
        # must implement transactional intent and reconciliation first.
        if definition.risk!="readonly":
            raise ContractViolation("external/write tools require explicit side-effect integration")
        result=impl(args)
        if not isinstance(result,dict):
            raise ContractViolation("tool result must be bounded JSON object")
        raw=canonical_bytes(result,ceiling=min(65536,ledger.remaining("output_bytes") or 1))
        ledger.charge(output_bytes=len(raw))
        output_digest=digest(result)
        self.journal.append(stream=session,event_id=event_id,kind="tool.executed",
                            payload={"name":name,"input_digest":signature,
                                     "output_digest":output_digest,"output":result})
        return ToolReceipt(name,invocation,signature,output_digest,result)
