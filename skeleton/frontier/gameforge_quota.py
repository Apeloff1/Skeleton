"""Hierarchical quota composition for bounded runtime admission."""
class Quota:
 def __init__(self,limit):
  if limit<=0: raise ValueError("limit must be positive")
  self.limit=limit; self.used=0
 def reserve(self,amount=1):
  if amount<=0: raise ValueError("amount must be positive")
  if self.used+amount>self.limit: return False
  self.used+=amount; return True
 def release(self,amount=1):
  if amount<=0 or amount>self.used: raise ValueError("invalid release")
  self.used-=amount
