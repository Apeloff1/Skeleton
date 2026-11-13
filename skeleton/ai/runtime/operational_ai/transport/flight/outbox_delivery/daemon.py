"""Operator-owned, synchronous private spool pump with bounded work per tick.

This is a separate local process, not a hidden server worker. The loop never
runs generated model instructions or remote callbacks. A failed export stops
processing, retains unacknowledged rows and leaves recovery to an operator.
"""
from __future__ import annotations
from dataclasses import dataclass
import signal,time
from threading import Event
from .contracts import DeliveryHeld
from .pump import DeliveryPump

@dataclass(frozen=True, slots=True)
class SpoolDaemonPolicy:
    tick_ms:int=250
    batch:int=32
    maximum_ticks:int=4096
    def __post_init__(self):
        if type(self.tick_ms)is not int or not 20<=self.tick_ms<=60000:
            raise DeliveryHeld('invalid bounded private spool tick interval')
        if type(self.batch)is not int or not 1<=self.batch<=128:
            raise DeliveryHeld('invalid spool export batch')
        if type(self.maximum_ticks)is not int or not 1<=self.maximum_ticks<=100000:
            raise DeliveryHeld('unbounded spool daemon rejected')

class LocalSpoolDaemon:
    def __init__(self,pump:DeliveryPump,policy:SpoolDaemonPolicy|None=None):
        if not isinstance(pump,DeliveryPump):raise DeliveryHeld('verified delivery pump required')
        self.pump=pump
        self.policy=policy or SpoolDaemonPolicy()
        self.stop=Event()
        self.ticks=0
        self.exported=0
        self.replayed=0
        self.state='new'
    def step(self)->dict:
        if self.state in ('held','stopped'):
            raise DeliveryHeld('spool daemon is no longer available')
        self.state='running'
        try:
            report=self.pump.drain(limit=min(self.policy.batch,self.pump.policy.max_batch))
        except BaseException:
            self.state='held'
            raise
        self.ticks+=1
        self.exported+=report['count']
        self.replayed+=report['replayed']
        return {'status':'active-private-spool','ticks':self.ticks,
                'exported':self.exported,'crash_replays':self.replayed,
                'model_calls':0,'remote_delivery':False}
    def run(self)->dict:
        if self.state!='new':raise DeliveryHeld('spool daemon cannot restart after execution')
        while not self.stop.is_set() and self.ticks<self.policy.maximum_ticks:
            last=self.step()
            if self.stop.wait(self.policy.tick_ms/1000):break
        if self.state!='held':self.state='stopped'
        return {'status':self.state,'ticks':self.ticks,'exported':self.exported,
                'crash_replays':self.replayed,'model_calls':0}
    def request_stop(self):
        self.stop.set()
