"""Fail-closed operation fence."""
class Fence:
    def __init__(self,open_:bool=True): self._open=open_
    def close(self)->None: self._open=False
    def open(self)->None: self._open=True
    def allow(self)->bool: return self._open
