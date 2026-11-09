"""Index execution receipt metadata for fast control-plane queries."""

from __future__ import annotations

from dataclasses import dataclass
import threading
from typing import Iterable

from skeleton.shells.receipts import ExecutionReceipt

@dataclass(frozen=True)
class ReceiptQuery:
    command:str|None=None
    correlation_id:str|None=None
    ok:bool|None=None
    timed_out:bool|None=None
    min_attempt:int|None=None

class ReceiptIndex:
    def __init__(self,*,max_receipts:int=100000)->None:
        if max_receipts<=0:
            raise ValueError("max_receipts must be positive")
        self.max_receipts=max_receipts
        self._by_id:dict[str,ExecutionReceipt]={}
        self._order:list[str]=[]
        self._lock=threading.RLock()

    def add(self,receipt:ExecutionReceipt)->None:
        with self._lock:
            if receipt.receipt_id in self._by_id:
                raise ValueError("receipt already indexed")
            self._by_id[receipt.receipt_id]=receipt
            self._order.append(receipt.receipt_id)
            if len(self._order)>self.max_receipts:
                evicted=self._order.pop(0)
                self._by_id.pop(evicted,None)

    def extend(self,receipts:Iterable[ExecutionReceipt])->None:
        for receipt in receipts:
            self.add(receipt)

    def get(self,receipt_id:str)->ExecutionReceipt:
        with self._lock:
            return self._by_id[receipt_id]

    def query(self,query:ReceiptQuery)->tuple[ExecutionReceipt,...]:
        with self._lock:
            result=[]
            for receipt_id in self._order:
                item=self._by_id[receipt_id]
                if query.command is not None and item.command!=query.command:
                    continue
                if query.correlation_id is not None and item.correlation_id!=query.correlation_id:
                    continue
                if query.ok is not None and item.ok is not query.ok:
                    continue
                if query.timed_out is not None and item.timed_out is not query.timed_out:
                    continue
                if query.min_attempt is not None and item.attempt<query.min_attempt:
                    continue
                result.append(item)
            return tuple(result)

    def remove(self,receipt_id:str)->bool:
        with self._lock:
            if receipt_id not in self._by_id:
                return False
            del self._by_id[receipt_id]
            self._order=[value for value in self._order if value!=receipt_id]
            return True

    def snapshot(self)->tuple[ExecutionReceipt,...]:
        with self._lock:
            return tuple(self._by_id[receipt_id] for receipt_id in self._order)
