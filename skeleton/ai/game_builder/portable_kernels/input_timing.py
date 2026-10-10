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

def source_frame_at(target_frame: int, source_hz: int, target_hz: int) -> int:
    """Recover the original simulation frame for a destination display frame."""
    index=_int(target_frame,"target frame ordinal",0,100000)
    source=_int(source_hz,"source refresh Hz",24,240)
    target=_int(target_hz,"target refresh Hz",24,240)
    return (index*source)//target


def edge_pressed(previous: int, current: int, mask: int=65535) -> int:
    """Only newly pressed controller bits trigger one-shot game actions."""
    prior=_buttons(previous)
    present=_buttons(current)
    include=_buttons(mask)
    return (~prior & present & include) & 65535


def edge_released(previous: int, current: int, mask: int=65535) -> int:
    """Edge-triggered release state, isolated from unrelated controller bits."""
    prior=_buttons(previous)
    present=_buttons(current)
    include=_buttons(mask)
    return (prior & ~present & include) & 65535


def deadzone_axis(value: int, *, threshold: int=4096) -> int:
    """Integer radial-independent controller-axis deadzone and rescale."""
    sample=_int(value,"signed controller axis",-32768,32767)
    dead=_int(threshold,"axis deadzone",0,32766)
    magnitude=abs(sample)
    if magnitude<=dead:
        return 0
    normalized=min(32767,(magnitude-dead)*32767//(32767-dead))
    return normalized if sample>0 else -normalized


def digital_hysteresis(samples: object, *, press: int=20000,
                       release: int=14000) -> tuple[bool,...]:
    """Schmitt-trigger analog button conversion without threshold chatter."""
    on=_int(press,"press threshold",1,32767)
    off=_int(release,"release threshold",0,on-1)
    if (not isinstance(samples,(tuple,list)) or not 1<=len(samples)<=4096
            or any(type(x) is not int or not 0<=x<=32767 for x in samples)):
        raise InputTimingError("bounded unsigned trigger samples required")
    pressed=False
    result=[]
    for sample in samples:
        if pressed and sample<=off:
            pressed=False
        elif not pressed and sample>=on:
            pressed=True
        result.append(pressed)
    return tuple(result)

