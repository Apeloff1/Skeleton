"""Deterministic deadline budget accounting."""
class Deadline:
 def __init__(self,budget:int):
  if budget<0: raise ValueError("budget must be non-negative")
  self.remaining=budget
 def spend(self,cost:int)->bool:
  if cost<0: raise ValueError("cost must be non-negative")
  if cost>self.remaining: self.remaining=0; return False
  self.remaining-=cost; return True
