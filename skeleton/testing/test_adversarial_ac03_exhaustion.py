from __future__ import annotations
import pytest

class Budget:
    def __init__(self, capacity: int): self.capacity=capacity; self.used=0
    def consume(self, amount: int=1):
        if amount<0 or self.used+amount>self.capacity: raise OSError("ENOSPC")
        self.used+=amount
    def release(self, amount: int=1): self.used=max(0,self.used-amount)

def test_hard_exhaustion_fails_closed():
    b=Budget(2); b.consume(); b.consume()
    with pytest.raises(OSError,match="ENOSPC"): b.consume()
    assert b.used==2

def test_recovery_after_release_does_not_overcommit():
    b=Budget(1); b.consume()
    with pytest.raises(OSError): b.consume()
    b.release(); b.consume(); assert b.used==1

def test_degraded_mode_preserves_budget_boundary():
    b=Budget(1); b.consume()
    with pytest.raises(OSError,match="ENOSPC"): b.consume()
    assert b.used <= b.capacity
