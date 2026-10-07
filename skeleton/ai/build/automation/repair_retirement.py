"""Require evidence that the originating blocker disappeared before retirement."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class Retirement:
 repair_id:str;retired:bool;reason:str
def evaluate(*,repair_id:str,original_gate:str,original_head:str,current_head:str,current_gate_green:bool,receipt_verified:bool)->Retirement:
 if current_head==original_head:return Retirement(repair_id,False,"repair has not produced a new exact head")
 if not receipt_verified:return Retirement(repair_id,False,"repair outcome receipt unverified")
 if not current_gate_green:return Retirement(repair_id,False,f"{original_gate} still failing")
 return Retirement(repair_id,True,"originating exact-head blocker cleared")
