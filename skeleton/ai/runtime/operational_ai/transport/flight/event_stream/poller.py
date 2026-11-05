"""Bounded long polling; no busy-loop, no writer transactions held while waiting."""
from __future__ import annotations
import time
from .contracts import StreamError,bounded
from .reader import EventReader,StreamSnapshot

def read_until(reader:EventReader,job:str,cursor:str|None,*,limit:int=32,
               wait_ms:int=0,clock=time.monotonic_ns,sleep=time.sleep)->StreamSnapshot:
    if not isinstance(reader,EventReader):
        raise StreamError('stream reader required')
    bounded(wait_ms,0,2000,'poll interval')
    deadline=clock()+wait_ms*1_000_000
    attempts=0
    while True:
        result=reader.read(job,cursor,limit=limit)
        if result.events or result.terminal or clock()>=deadline:
            return result
        attempts+=1
        if attempts>80:
            raise StreamError('bounded stream poll attempt ceiling reached')
        remaining=(deadline-clock())/1_000_000_000
        if remaining<=0:return result
        sleep(min(0.04,remaining))
