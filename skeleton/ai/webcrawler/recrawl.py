"""Adaptive recrawl scheduler based on observed change cadence and source value."""
from __future__ import annotations
import heapq,math
from dataclasses import dataclass,field
from urllib.parse import urlsplit

@dataclass(order=True)
class RecrawlItem:
    due_at:float
    sequence:int
    url:str=field(compare=False)
    interval:float=field(compare=False)
    priority:float=field(compare=False,default=0.0)

class RecrawlScheduler:
    def __init__(self,min_interval=300.0,max_interval=30*86400.0):
        self.minimum=min_interval;self.maximum=max_interval;self._heap=[];self._seq=0;self._state={}
    def observe(self,url:str,*,now:float,changed:bool,source_score:float=.5)->RecrawlItem:
        previous=self._state.get(url)
        interval=previous.interval if previous else self.minimum
        # Changed/high-value sources tighten; stable sources back off geometrically.
        if changed:interval=max(self.minimum,interval*.5)
        else:interval=min(self.maximum,interval*2.0)
        value=max(.05,min(1.0,source_score))
        interval=max(self.minimum,min(self.maximum,interval/(.75+.5*value)))
        self._seq+=1
        item=RecrawlItem(now+interval,self._seq,url,interval,value)
        self._state[url]=item;heapq.heappush(self._heap,item);return item
    def due(self,*,now:float,limit:int=100)->list[RecrawlItem]:
        out=[]
        while self._heap and len(out)<limit and self._heap[0].due_at<=now:
            item=heapq.heappop(self._heap)
            if self._state.get(item.url) is item:out.append(item)
        return out
    def next_due(self)->float|None:
        while self._heap and self._state.get(self._heap[0].url) is not self._heap[0]:heapq.heappop(self._heap)
        return self._heap[0].due_at if self._heap else None
