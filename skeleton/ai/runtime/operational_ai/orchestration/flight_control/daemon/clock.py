"""Monotonic daemon liveness; boot-bound leases belong to FlightLedger."""
from __future__ import annotations
import time

def now_ns()->int:
    return time.monotonic_ns()

def age_ms(then_ns:int,now:int)->int:
    if type(then_ns)is not int or type(now)is not int:
        raise TypeError('monotonic counters must be integers')
    return max(0,(now-then_ns)//1_000_000)
