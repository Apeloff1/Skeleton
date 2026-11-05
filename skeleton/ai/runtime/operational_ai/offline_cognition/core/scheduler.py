"""Weighted fair scheduling, interval admission and deterministic queue ordering."""
from __future__ import annotations
import heapq
from dataclasses import dataclass
from threading import RLock
from .contracts import identifier,integer,number,refuse
@dataclass(frozen=True,slots=True)
class Task:
    job_id:str
    tenant:str
    cost:int
    priority:int
    deadline_ns:int
    def __post_init__(self):
        identifier(self.job_id);identifier(self.tenant)
        integer(self.cost,minimum=1,maximum=262144)
        integer(self.priority,maximum=10000)
        integer(self.deadline_ns,minimum=1)
class FairQueue:
    def __init__(self,*,maximum=10000):
        integer(maximum,minimum=1,maximum=100000)
        self.max=maximum;self.lock=RLock();self.entries={}
        self.last_finish={};self.virtual_time=0.0;self.counter=0
    def enqueue(self,task,*,weight):
        if type(task) is not Task:refuse("typed native task required")
        weight=number(weight,minimum=0.001,maximum=10000)
        with self.lock:
            if len(self.entries)>=self.max:refuse("task queue saturated")
            if task.job_id in self.entries:refuse("duplicate task ID")
            finish=max(self.virtual_time,self.last_finish.get(task.tenant,0.0))+task.cost/weight
            self.last_finish[task.tenant]=finish
            self.entries[task.job_id]=(finish,self.counter,task)
            self.counter+=1
            return {"job_id":task.job_id,"virtual_finish":finish}
    def admit(self,*,now_ns,capacity_tokens):
        integer(now_ns);integer(capacity_tokens,minimum=1,maximum=262144)
        with self.lock:
            candidates=sorted(self.entries.values(),key=lambda x:(x[0],-x[2].priority,x[1]))
            remaining=capacity_tokens;admitted=[];expired=[]
            for finish,_,task in candidates:
                if now_ns>=task.deadline_ns:
                    expired.append(task.job_id);del self.entries[task.job_id]
                elif task.cost<=remaining:
                    admitted.append(task.job_id);remaining-=task.cost
                    self.virtual_time=max(self.virtual_time,finish)
                    del self.entries[task.job_id]
            return {"admitted":tuple(admitted),"expired":tuple(expired),
                    "remaining_tokens":remaining,"pending":len(self.entries)}
    def snapshot(self):
        with self.lock:return {"pending":len(self.entries),
                               "virtual_time":self.virtual_time,
                               "tenants":tuple(sorted({v[2].tenant for v in self.entries.values()}))}
