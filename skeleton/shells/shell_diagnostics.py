"""Cross-component diagnostics for the shell execution plane."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.shells.cancellation import CancellationRegistry
from skeleton.shells.command_budget import CommandBudgets
from skeleton.shells.concurrency import WeightedConcurrency
from skeleton.shells.health import inspect_policy
from skeleton.shells.receipts import ReceiptChain
from skeleton.shells.runner import ShellRunner

class ShellDiagnosticSeverity(str,Enum):
    INFO="info"
    WARNING="warning"
    ERROR="error"

@dataclass(frozen=True)
class ShellDiagnostic:
    severity:ShellDiagnosticSeverity
    code:str
    message:str
    def to_dict(self)->dict[str,str]:
        return {"severity":self.severity.value,"code":self.code,"message":self.message}

@dataclass(frozen=True)
class ShellDiagnosticsReport:
    findings:tuple[ShellDiagnostic,...]
    @property
    def errors(self)->int:
        return sum(item.severity is ShellDiagnosticSeverity.ERROR for item in self.findings)
    @property
    def warnings(self)->int:
        return sum(item.severity is ShellDiagnosticSeverity.WARNING for item in self.findings)
    @property
    def ok(self)->bool:
        return self.errors==0
    def to_dict(self)->dict[str,object]:
        return {"ok":self.ok,"errors":self.errors,"warnings":self.warnings,"findings":[x.to_dict() for x in self.findings]}

class ShellDiagnostics:
    def __init__(
        self,
        *,
        runner:ShellRunner,
        receipts:ReceiptChain|None=None,
        cancellations:CancellationRegistry|None=None,
        concurrency:WeightedConcurrency|None=None,
        budgets:CommandBudgets|None=None,
    )->None:
        self.runner=runner
        self.receipts=receipts
        self.cancellations=cancellations
        self.concurrency=concurrency
        self.budgets=budgets

    def inspect(self)->ShellDiagnosticsReport:
        findings=[]
        health=inspect_policy(self.runner.policy)
        if not health.healthy:
            findings.append(ShellDiagnostic(ShellDiagnosticSeverity.ERROR,"policy_unhealthy","shell policy health check failed"))
        if self.receipts is not None and not self.receipts.verify():
            findings.append(ShellDiagnostic(ShellDiagnosticSeverity.ERROR,"receipt_chain_invalid","receipt chain verification failed"))
        if self.cancellations is not None:
            cancelled=self.cancellations.cancelled()
            if cancelled:
                findings.append(ShellDiagnostic(ShellDiagnosticSeverity.INFO,"cancelled_operations",f"{len(cancelled)} cancelled operation tokens retained"))
        if self.concurrency is not None:
            snap=self.concurrency.snapshot()
            if snap.used>snap.capacity:
                findings.append(ShellDiagnostic(ShellDiagnosticSeverity.ERROR,"concurrency_overcommitted","weighted concurrency exceeds capacity"))
            elif snap.available==0:
                findings.append(ShellDiagnostic(ShellDiagnosticSeverity.WARNING,"concurrency_saturated","weighted concurrency is saturated"))
        if self.budgets is not None:
            denied=[command for command in self.budgets.snapshot() if not self.budgets.inspect(command).allowed]
            if denied:
                findings.append(ShellDiagnostic(ShellDiagnosticSeverity.WARNING,"command_budget_exhausted",f"{len(denied)} command budgets exhausted"))
        return ShellDiagnosticsReport(tuple(findings))
