"""Deterministic per-frame input and refresh conversion for homebrew ports."""
from __future__ import annotations
from collections.abc import Mapping

class InputTimingError(ValueError):
    """Invalid controller state, frame cadence or bounded event stream."""

def _int(value: object, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise InputTimingError(f"invalid {name}")
    return value

def _buttons(value: object) -> int:
    return _int(value,"16-bit controller mask",0,65535)


def frame_schedule(source_hz: int, target_hz: int, frames: int) -> tuple[int,...]:
    """Exact rational refresh conversion: target frames emitted per source tick."""
    source=_int(source_hz,"source refresh Hz",24,240)
    target=_int(target_hz,"target refresh Hz",24,240)
    count=_int(frames,"source frame count",1,10000)
    return tuple(((i+1)*target)//source - (i*target)//source for i in range(count))
