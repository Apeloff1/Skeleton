"""Reconcile shell control-plane evidence into actionable findings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.shells.command_budget import CommandBudgets
from skeleton.shells.concurrency import WeightedConcurrency
from skeleton.shells.failure_ledger import ShellFailureLedger
from skeleton.shells.receipts import ReceiptChain
from skeleton.shells.shell_events import ShellEvents

class ReconcileSeverity(str,Enum):
    INFO="info"
    WARNING="warning"
    ERROR="error"

@dataclass(frozen=True)
class ReconcileFinding:
    severity:ReconcileSeverity
    code:str
    message:str

    def to_dict(self)->dict[str,str]:
        return {"severity":self.severity.value,"code":self.code,"message":self.message}

@dataclass(frozen=True)
class ReconcileReport:
    findings:tuple[ReconcileFinding,...]

    @property
    def errors(self)->int:
        return sum(item.severity is ReconcileSeverity.ERROR for item in self.findings)

    @property
    def ok(self)->bool:
        return self.errors==0

    def to_dict(self)->dict[str,object]:
        return {"ok":self.ok,"errors":self.errors,"findings":[item.to_dict() for item in self.findings]}

class ShellReconciler:
    def __init__(
        self,
        *,
        receipts:ReceiptChain|None=None,
        events:ShellEvents|None=None,
        failures:ShellFailureLedger|None=None,
        concurrency:WeightedConcurrency|None=None,
        budgets:CommandBudgets|None=None,
    )->None:
        self.receipts=receipts
        self.events=events
        self.failures=failures
        self.concurrency=concurrency
        self.budgets=budgets

    def reconcile(self)->ReconcileReport:
        findings=[]
        if self.receipts is not None and not self.receipts.verify():
            findings.append(ReconcileFinding(ReconcileSeverity.ERROR,"receipt_chain_invalid","receipt evidence chain is invalid"))
        if self.concurrency is not None:
            snap=self.concurrency.snapshot()
            if snap.used>snap.capacity:
                findings.append(ReconcileFinding(ReconcileSeverity.ERROR,"concurrency_overcommit","concurrency usage exceeds capacity"))
            elif snap.permits and snap.used==0:
                findings.append(ReconcileFinding(ReconcileSeverity.ERROR,"permit_accounting_mismatch","permits exist with zero used weight"))
        if self.budgets is not None:
            denied=[name for name in self.budgets.snapshot() if not self.budgets.inspect(name).allowed]
            if denied:
                findings.append(ReconcileFinding(ReconcileSeverity.WARNING,"budgets_exhausted",f"{len(denied)} command budgets exhausted"))
        if self.failures is not None:
            counts=self.failures.counts()
            internal=counts.get("internal",0)
            if internal:
                findings.append(ReconcileFinding(ReconcileSeverity.WARNING,"internal_failures",f"{internal} internal shell failures recorded"))
        if self.events is not None:
            starts=len(self.events.query(kind="shell.dispatch.started"))
            finishes=len(self.events.query(kind="shell.dispatch.completed"))+len(self.events.query(kind="shell.dispatch.error"))
            if finishes>starts:
                findings.append(ReconcileFinding(ReconcileSeverity.ERROR,"event_order_invalid","more terminal dispatch events than starts"))
            elif starts>finishes:
                findings.append(ReconcileFinding(ReconcileSeverity.INFO,"dispatches_inflight",f"{starts-finishes} dispatches have no terminal event"))
        return ReconcileReport(tuple(findings))
