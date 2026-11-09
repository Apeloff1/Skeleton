"""Canonical aggregate shell-plane snapshots."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import time
from typing import Callable

from skeleton.shells.cancellation import CancellationRegistry
from skeleton.shells.command_budget import CommandBudgets
from skeleton.shells.concurrency import WeightedConcurrency
from skeleton.shells.receipts import ReceiptChain
from skeleton.shells.shell_diagnostics import ShellDiagnostics
from skeleton.shells.status import ShellPlaneStatus

@dataclass(frozen=True)
class ShellSnapshot:
    schema_version:int
    created_at:float
    status:dict[str,object]
    diagnostics:dict[str,object]
    cancellations:dict[str,object]
    concurrency:dict[str,object]
    budgets:dict[str,object]
    receipt_root:str|None

    def to_dict(self)->dict[str,object]:
        return {
            "schema_version":self.schema_version,
            "created_at":self.created_at,
            "status":self.status,
            "diagnostics":self.diagnostics,
            "cancellations":self.cancellations,
            "concurrency":self.concurrency,
            "budgets":self.budgets,
            "receipt_root":self.receipt_root,
        }

    @property
    def digest(self)->str:
        raw=json.dumps(self.to_dict(),sort_keys=True,separators=(",",":"),default=str).encode()
        return hashlib.sha256(raw).hexdigest()

class ShellSnapshotter:
    def __init__(
        self,
        *,
        status_provider:Callable[[],ShellPlaneStatus],
        diagnostics:ShellDiagnostics,
        cancellations:CancellationRegistry,
        concurrency:WeightedConcurrency,
        budgets:CommandBudgets,
        receipts:ReceiptChain|None=None,
        clock:Callable[[],float]=time.monotonic,
    )->None:
        self.status_provider=status_provider
        self.diagnostics=diagnostics
        self.cancellations=cancellations
        self.concurrency=concurrency
        self.budgets=budgets
        self.receipts=receipts
        self._clock=clock

    def capture(self)->ShellSnapshot:
        cancellation={
            key:value.to_dict() for key,value in self.cancellations.snapshot().items()
        }
        budgets={
            key:value.to_dict() for key,value in self.budgets.snapshot().items()
        }
        return ShellSnapshot(
            1,
            self._clock(),
            self.status_provider().to_dict(),
            self.diagnostics.inspect().to_dict(),
            cancellation,
            self.concurrency.snapshot().to_dict(),
            budgets,
            None if self.receipts is None else self.receipts.root_hash(),
        )
