"""Deterministic multidimensional resource admission and fair budget partition."""
from __future__ import annotations
from dataclasses import dataclass
from .contracts import integer,number,identifier,refuse
@dataclass(frozen=True,slots=True)
class Resource:
    tokens:int
    bytes:int
    milliseconds:int
    slots:int=1
    def __post_init__(self):
        integer(self.tokens,maximum=262144)
        integer(self.bytes,maximum=2**40)
        integer(self.milliseconds,maximum=3_600_000)
        integer(self.slots,maximum=100000)
    def add(self,other):
        if type(other) is not Resource:refuse("resource accounting type confusion")
        return Resource(self.tokens+other.tokens,self.bytes+other.bytes,
                        self.milliseconds+other.milliseconds,self.slots+other.slots)
    def subtract(self,other):
        if type(other) is not Resource:refuse("resource reservation type confusion")
        if any(getattr(other,k)>getattr(self,k) for k in ("tokens","bytes","milliseconds","slots")):
            refuse("resource reservation exceeds remaining budget")
        return Resource(self.tokens-other.tokens,self.bytes-other.bytes,
                        self.milliseconds-other.milliseconds,self.slots-other.slots)
    def fits(self,capacity):
        if type(capacity) is not Resource:refuse("capacity type mismatch")
        return all(getattr(self,k)<=getattr(capacity,k)
                   for k in ("tokens","bytes","milliseconds","slots"))
def partition(total,weights):
    if type(total) is not int or total<0:refuse("finite total capacity required")
    if type(weights) is not dict or not 1<=len(weights)<=10000:
        refuse("bounded resource recipients required")
    for actor,w in weights.items():
        identifier(actor);number(w,minimum=0,maximum=1e9)
    grand=sum(weights.values())
    if grand<=0:refuse("zero weight admission policy")
    shares={actor:int(total*w/grand) for actor,w in weights.items()}
    remaining=total-sum(shares.values())
    fractional=sorted(weights,key=lambda k:(-(total*weights[k]/grand-shares[k]),k))
    for actor in fractional[:remaining]:shares[actor]+=1
    if sum(shares.values())!=total:refuse("resource accounting conservation failed")
    return shares
def reserve_batch(capacity,candidates):
    if type(capacity) is not Resource or type(candidates) not in (tuple,list):
        refuse("bounded resource batch required")
    if len(candidates)>4096:refuse("candidate batch ceiling")
    remaining=capacity;selected=[];held=[]
    seen=set()
    for identifier_value,need in candidates:
        identifier(identifier_value)
        if identifier_value in seen:refuse("duplicate operation reservation")
        seen.add(identifier_value)
        if type(need) is not Resource:refuse("invalid job budget")
        if need.fits(remaining):
            remaining=remaining.subtract(need);selected.append(identifier_value)
        else:held.append(identifier_value)
    return {"admitted":tuple(selected),"held":tuple(held),"remaining":remaining}
