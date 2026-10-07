"""Consumable execution budget for bounded autonomous work."""
from __future__ import annotations
from dataclasses import dataclass, replace
@dataclass(frozen=True)
class ExecutionBudget:
    model_calls:int=24; validation_seconds:int=360; patch_chars:int=72_000; files:int=24
    def consume(self,*,model_calls:int=0,validation_seconds:int=0,patch_chars:int=0,files:int=0):
        values=(model_calls,validation_seconds,patch_chars,files)
        if any(v<0 for v in values): raise ValueError("budget consumption cannot be negative")
        nxt=replace(self,model_calls=self.model_calls-model_calls,validation_seconds=self.validation_seconds-validation_seconds,patch_chars=self.patch_chars-patch_chars,files=self.files-files)
        if min(nxt.model_calls,nxt.validation_seconds,nxt.patch_chars,nxt.files)<0: raise ValueError("Studio execution budget exhausted")
        return nxt
