"""Original PSG and deterministic PCM helpers for lawful homebrew sound."""
from __future__ import annotations

class AudioKernelError(ValueError):
    """PCM buffer, timing or retro sound-chip parameter is invalid."""

def _integer(value: object, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise AudioKernelError(f"{name} must be an integer in {low}..{high}")
    return value

def _pcm(samples: object, max_samples: int=32768) -> tuple[int,...]:
    if (not isinstance(samples,(tuple,list)) or not 1 <= len(samples) <= max_samples
            or any(type(v) is not int or not -32768 <= v <= 32767 for v in samples)):
        raise AudioKernelError("bounded signed PCM16 samples required")
    return tuple(samples)


def gameboy_pulse_period(hertz: int) -> int:
    """Convert an audio note to Game Boy NR13/NR14 11-bit period."""
    hz=_integer(hertz,"Game Boy tone Hz",64,131072)
    return max(0,min(2047,2048-(131072+hz//2)//hz))


def gameboy_pulse_frequency(period: int) -> float:
    """Recover an actual Game Boy pulse tone's frequency from 11-bit period."""
    return round(131072/(2048-_integer(period,"Game Boy tone period",0,2047)),6)


def nes_pulse_timer(hertz: int) -> int:
    """NTSC 2A03 APU pulse timer with CPU divider 16 and 11-bit range."""
    hz=_integer(hertz,"NES pulse Hz",55,111860)
    return max(0,min(2047,(1789773+8*hz)//(16*hz)-1))

