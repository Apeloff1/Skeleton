"""Monotonic checkpoint contract for replay-safe consumers."""
class Checkpoint:
    def __init__(self,sequence:int=-1):
        if sequence < -1: raise ValueError("sequence must be >= -1")
        self._sequence=sequence
    def advance(self,sequence:int)->bool:
        if sequence<0: raise ValueError("sequence must be non-negative")
        if sequence<=self._sequence: return False
        self._sequence=sequence; return True
    @property
    def sequence(self): return self._sequence
