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


def sn76489_tone_period(hertz: int, *, master_clock: int=3579545) -> int:
    """SN76489 Sega TI PSG 10-bit tone divider, never a zero divider."""
    hz=_integer(hertz,"SN tone Hz",110,125000)
    clock=_integer(master_clock,"PSG clock",1000000,8000000)
    return max(1,min(1023,(clock+16*hz)//(32*hz)))


def ay38910_tone_period(hertz: int, *, master_clock: int=1773400) -> int:
    """AY-3-8910/YM2149 12-bit square-wave period."""
    hz=_integer(hertz,"AY tone Hz",27,110837)
    clock=_integer(master_clock,"AY clock",1000000,8000000)
    return max(1,min(4095,(clock+8*hz)//(16*hz)))


def pulse_pcm(hertz: int, sample_rate: int, count: int,
              *, duty_num: int=1, duty_den: int=2) -> tuple[int,...]:
    """Integer-phase signed PCM pulse oscillator with bounded duty cycle."""
    rate=_integer(sample_rate,"PCM sample rate",4000,96000)
    hz=_integer(hertz,"pulse oscillator Hz",1,rate//2)
    samples=_integer(count,"PCM sample count",1,32768)
    denominator=_integer(duty_den,"duty denominator",2,64)
    numerator=_integer(duty_num,"duty numerator",1,denominator-1)
    duration=rate*denominator
    threshold=rate*numerator
    return tuple(32767 if (i*hz*denominator)%duration < threshold else -32767
                 for i in range(samples))


def triangle_pcm(hertz: int, sample_rate: int, count: int) -> tuple[int,...]:
    """Aliasing-admitted deterministic signed triangle tone using integer phase."""
    rate=_integer(sample_rate,"PCM sample rate",4000,96000)
    hz=_integer(hertz,"triangle Hz",1,rate//2)
    samples=_integer(count,"PCM sample count",1,32768)
    return tuple(32767 - (65534*abs(2*((i*hz)%rate)-rate)+rate//2)//rate
                 for i in range(samples))


def noise_lfsr_pcm(seed: int, count: int) -> tuple[int,...]:
    """Deterministic 15-bit PSG-style XOR feedback noise from an explicit seed."""
    state=_integer(seed,"LFSR seed",1,0x7fff)
    samples=_integer(count,"PCM sample count",1,32768)
    out=[]
    for _ in range(samples):
        out.append(32767 if state&1 else -32767)
        feedback=(state^(state>>1))&1
        state=(state>>1)|(feedback<<14)
    return tuple(out)
