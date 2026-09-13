"""Hierarchical budget: child reservations cannot exceed parent capacity."""
class Budget:
 def __init__(self,capacity:int):
  if capacity<=0: raise ValueError("capacity must be positive")
  self.capacity=capacity; self.used=0
 def reserve(self,amount:int=1)->bool:
  if amount<=0: raise ValueError("amount must be positive")
  if self.used+amount>self.capacity: return False
  self.used+=amount; return True
 def release(self,amount:int=1):
  if amount<=0 or amount>self.used: raise ValueError("invalid release")
  self.used-=amount
