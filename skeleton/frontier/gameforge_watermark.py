"""Monotonic high-water mark contract."""
class Watermark:
    def __init__(self,value:int=-1):
        if value< -1: raise ValueError("invalid watermark")
        self._value=value
    def observe(self,value:int)->None:
        if value<0: raise ValueError("value must be non-negative")
        if value>self._value: self._value=value
    @property
    def value(self)->int: return self._value
