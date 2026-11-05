"""Privacy-minimizing operation metrics with bounded labels and stable export."""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
import threading

_ALLOWED={'inference','context','retrieval','memory','tool','transport','evaluation','storage'}
_STATES={'ok','blocked','failed','cancelled','timeout'}

class OperationalMetrics:
    def __init__(self):self._lock=threading.RLock();self._counts=defaultdict(int);self._durations=defaultdict(list)

    def observe(self,plane:str,state:str,*,duration_ns:int|None=None)->None:
        if plane not in _ALLOWED or state not in _STATES:
            raise ValueError('metric labels must be bounded and non-personal')
        if duration_ns is not None and (type(duration_ns) is not int or duration_ns<0):
            raise ValueError('invalid metric duration')
        with self._lock:
            self._counts[(plane,state)]+=1
            if duration_ns is not None:
                arr=self._durations[(plane,state)]
                if len(arr)<10000:arr.append(duration_ns)

    def snapshot(self)->dict:
        with self._lock:
            return {'counts':{f'{k[0]}.{k[1]}':v for k,v in sorted(self._counts.items())},
                    'durations_ns':{f'{k[0]}.{k[1]}':{'count':len(v),'max':max(v) if v else 0}
                          for k,v in sorted(self._durations.items())}}
