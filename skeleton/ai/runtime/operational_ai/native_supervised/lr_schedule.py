"""Deterministic cosine SGD rate schedule; finite, bounded and replayable."""
from __future__ import annotations
import math
from .canonical import require_int
from .errors import reject


def learning_rate(step:int,total:int,base_ppm:int,*,floor_ppm:int=100)->float:
    require_int(total,"schedule-total",1,1000000)
    require_int(step,"schedule-step",0,total-1)
    require_int(base_ppm,"schedule-base",1,100000)
    require_int(floor_ppm,"schedule-floor",0,100000)
    if floor_ppm>base_ppm:
        reject("schedule-floor-over-base")
    fraction=(1.0+math.cos(math.pi*step/max(1,total-1)))/2.0
    rate=floor_ppm+(base_ppm-floor_ppm)*fraction
    result=rate/1000000.0
    if not math.isfinite(result) or result<=0:
        reject("schedule-nonfinite-rate")
    return result
