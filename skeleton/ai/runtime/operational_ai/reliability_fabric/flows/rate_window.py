"""Deterministic fixed-window local admission limiter without time.sleep or busy wait."""
from __future__ import annotations
from collections import defaultdict
from threading import RLock
import time
from ..contracts import fail

class RateWindow:
    def __init__(self,*,max_calls=32,period_ns=1_000_000_000,
                 clock=time.monotonic_ns,maximum_tenants=1024):
        if any(type(x) is not int for x in (max_calls,period_ns,maximum_tenants)):
            fail("rate limits require exact integers")
        if not 1<=max_calls<=100000 or not 1<=period_ns<=3600000000000:
            fail("invalid fixed-window rate")
        if not 1<=maximum_tenants<=100000:fail("unbounded tenant registry")
        if not callable(clock):fail("trusted monotonic clock required")
        self._max=max_calls;self._period=period_ns
        self._clock=clock;self._tenant_max=maximum_tenants
        self._lock=RLock();self._records={}

    def admit(self,tenant):
        if type(tenant) is not str or not tenant or len(tenant)>48:
            fail("invalid actor for rate admission")
        now=self._clock()
        if type(now) is not int or now<0:fail("invalid rate clock")
        period=now//self._period
        with self._lock:
            if tenant not in self._records and len(self._records)>=self._tenant_max:
                # A capacity-full table cannot quietly bypass quotas.
                fail("rate table full")
            old_period,old_count=self._records.get(tenant,(period,0))
            if old_period>period:fail("monotonic rate period moved backwards")
            count=old_count if old_period==period else 0
            if count>=self._max:fail("caller rate window saturated")
            self._records[tenant]=(period,count+1)
            return {"tenant":tenant,"period":period,"admitted":count+1,
                    "ceiling":self._max}

    def snapshot(self):
        with self._lock:return dict(self._records)
