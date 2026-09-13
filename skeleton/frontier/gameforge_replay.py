"""Replay cursor that skips already checkpointed events."""
class ReplayCursor:
 def __init__(self,checkpoint=-1): self.checkpoint=checkpoint
 def consume(self,events):
  fresh=[e for e in events if e.sequence>self.checkpoint]
  if fresh: self.checkpoint=fresh[-1].sequence
  return tuple(fresh)
