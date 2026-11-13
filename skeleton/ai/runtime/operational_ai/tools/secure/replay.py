"""Tool receipt ledger suitable for comparing replay outputs without reexecution."""
from __future__ import annotations
from dataclasses import dataclass, field
from .receipts import ToolExecutionReceipt
from .spec import ToolError

@dataclass(slots=True)
class ReceiptLedger:
    max_receipts:int=1024
    _records:dict=field(default_factory=dict,init=False,repr=False)
    def __post_init__(self):
        if type(self.max_receipts) is not int or not 1<=self.max_receipts<=100000:
            raise ToolError('invalid replay receipt ceiling')
        self._records={}

    def admit(self,scope:tuple[str,str,str],receipt:ToolExecutionReceipt)->bool:
        if len(scope)!=3:raise ToolError('invalid ledger scope')
        key=(*scope,receipt.invocation_id)
        existing=self._records.get(key)
        if existing is not None:
            if existing!=receipt:raise ToolError('incompatible receipt for replay identity')
            return False
        if len(self._records)>=self.max_receipts:raise ToolError('receipt ledger capacity exceeded')
        self._records[key]=receipt
        return True

    def lookup(self,scope:tuple[str,str,str],invocation_id:str)->ToolExecutionReceipt|None:
        return self._records.get((*scope,invocation_id))
