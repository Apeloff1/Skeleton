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


def axis_to_eightway(x: int, y: int, *, threshold: int=8192) -> str:
    """Map analog axes to original eight-way pads with stable neutral zone."""
    horizontal=_int(x,"horizontal axis",-32768,32767)
    vertical=_int(y,"vertical axis",-32768,32767)
    dead=_int(threshold,"eightway deadzone",0,32766)
    ns="n" if vertical < -dead else "s" if vertical > dead else ""
    ew="w" if horizontal < -dead else "e" if horizontal > dead else ""
    return ns+ew if ns or ew else "neutral"


def debounce_buttons(samples: object, *, stable_frames: int=2) -> tuple[int,...]:
    """Suppress noisy mechanical switch chatter before updating button state."""
    needed=_int(stable_frames,"button debounce frames",1,120)
    if not isinstance(samples,(tuple,list)) or not 1<=len(samples)<=4096:
        raise InputTimingError("bounded button samples required")
    masks=tuple(_buttons(s) for s in samples)
    accepted=0
    candidate=0
    streak=0
    result=[]
    for state in masks:
        if state!=candidate:
            candidate=state
            streak=1
        else:
            streak+=1
        if streak>=needed:
            accepted=candidate
        result.append(accepted)
    return tuple(result)


def button_auto_repeat(pressed: object, *, delay: int=20,
                       interval: int=5) -> tuple[bool,...]:
    """Deterministic keyboard/gamepad repeat on the simulation frame clock."""
    wait=_int(delay,"repeat delay",1,240)
    period=_int(interval,"repeat interval",1,120)
    if (not isinstance(pressed,(tuple,list)) or not 1<=len(pressed)<=4096
            or any(type(x) is not bool for x in pressed)):
        raise InputTimingError("boolean held-button frame sequence required")
    held=0
    result=[]
    for state in pressed:
        held=held+1 if state else 0
        age=held-1
        result.append(bool(held and (held==1 or (age>=wait and (age-wait)%period==0))))
    return tuple(result)


def remap_buttons(mask: int, mapping: object) -> int:
    """Injective 16-button port remapping; refuse dropped or colliding actions."""
    value=_buttons(mask)
    if not isinstance(mapping,Mapping) or not 1<=len(mapping)<=16:
        raise InputTimingError("bounded button mapping required")
    used_from=0
    used_to=0
    for source,target in mapping.items():
        start=_int(source,"mapping source bit",1,32768)
        destination=_int(target,"mapping destination bit",1,32768)
        if (start&(start-1)) or (destination&(destination-1)):
            raise InputTimingError("button mapping requires exact one-hot masks")
        if used_from&start or used_to&destination:
            raise InputTimingError("ambiguous mapping collision")
        used_from|=start
        used_to|=destination
    if value&~used_from:
        raise InputTimingError("controller state has unmapped held actions")
    out=0
    for source,destination in mapping.items():
        if value&source:
            out|=destination
    return out
