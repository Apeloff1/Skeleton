"""Circuit breaker with monotonic open/close transitions."""
from enum import Enum
class CircuitState(str,Enum): CLOSED="closed"; OPEN="open"; HALF_OPEN="half_open"
class Circuit:
 def __init__(self,threshold:int=5):
  if threshold<=0: raise ValueError("threshold must be positive")
  self.threshold=threshold; self.failures=0; self.state=CircuitState.CLOSED
 def failure(self):
  self.failures+=1
  if self.failures>=self.threshold: self.state=CircuitState.OPEN
 def probe(self):
  if self.state is CircuitState.OPEN: self.state=CircuitState.HALF_OPEN; return True
  return self.state is CircuitState.HALF_OPEN
 def success(self): self.failures=0; self.state=CircuitState.CLOSED
