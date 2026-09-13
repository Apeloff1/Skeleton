"""Bounded retry budget preventing unbounded recovery amplification."""
class RetryBudget:
 def __init__(self,attempts):
  if attempts<0: raise ValueError("attempts must be non-negative")
  self.remaining=attempts
 def consume(self):
  if self.remaining<=0: return False
  self.remaining-=1; return True
