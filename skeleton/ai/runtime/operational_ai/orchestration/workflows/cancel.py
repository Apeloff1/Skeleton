"""Cooperative cancellation with parent-child propagation and monotonic deadlines."""
from __future__ import annotations
import threading,time
from .graph import WorkflowError

class Cancellation:
    def __init__(self,deadline_ns:int,*,parent:'Cancellation|None'=None):
        if type(deadline_ns) is not int or deadline_ns<=0:
            raise WorkflowError('invalid absolute cancellation deadline')
        self.deadline_ns=deadline_ns
        self.parent=parent
        self._event=threading.Event()

    def cancel(self)->None:self._event.set()

    def checkpoint(self)->None:
        if self._event.is_set() or (self.parent is not None and self.parent.cancelled):
            raise WorkflowError('operation cancelled')
        if time.monotonic_ns()>=self.deadline_ns:
            raise WorkflowError('operation deadline expired')

    @property
    def cancelled(self)->bool:
        return self._event.is_set() or time.monotonic_ns()>=self.deadline_ns or bool(self.parent and self.parent.cancelled)

    def child(self,*,budget_ms:int)->'Cancellation':
        if type(budget_ms) is not int or not 1<=budget_ms<=600_000:
            raise WorkflowError('invalid child deadline')
        return Cancellation(min(self.deadline_ns,time.monotonic_ns()+budget_ms*1_000_000),parent=self)
