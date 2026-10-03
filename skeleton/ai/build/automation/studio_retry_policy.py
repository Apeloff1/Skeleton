"""Deterministic repair/retry decisions."""
from __future__ import annotations
from dataclasses import dataclass
@dataclass(frozen=True)
class RetryDecision:
    action:str; delay_cycles:int; reason:str
def decide(*,attempt:int,validation_failed:bool,structural_failure:bool)->RetryDecision:
    if attempt<0: raise ValueError("attempt cannot be negative")
    if structural_failure: return RetryDecision("reject",0,"structural boundary failure")
    if not validation_failed: return RetryDecision("accept",0,"validation passed")
    if attempt>=3: return RetryDecision("quarantine",0,"repair budget exhausted")
    return RetryDecision("repair",min(8,2**attempt),"validation failed")
