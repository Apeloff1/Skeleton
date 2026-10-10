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

def adsr_envelope(count: int, *, attack: int, decay: int,
                  sustain: int, release: int) -> tuple[int,...]:
    """Bounded PCM amplitude envelope with exact finite stage lengths."""
    length=_integer(count,"ADSR sample count",1,32768)
    a=_integer(attack,"ADSR attack",0,length)
    d=_integer(decay,"ADSR decay",0,length)
    r=_integer(release,"ADSR release",0,length)
    level=_integer(sustain,"ADSR sustain level",0,32767)
    if a+d+r>length:
        raise AudioKernelError("ADSR stages exceed available samples")
    result=[]
    for i in range(length):
        if i<a:
            gain=32767*(i+1)//a
        elif i<a+d:
            gain=32767+(level-32767)*(i-a+1)//d
        elif r and i>=length-r:
            gain=level*(length-i-1)//r
        else:
            gain=level
        result.append(max(0,min(32767,gain)))
    return tuple(result)

def resample_linear(samples: object, source_rate: int, target_rate: int) -> tuple[int,...]:
    """Deterministic PCM16 rate adaptation with exact rational positions."""
    data=_pcm(samples)
    source=_integer(source_rate,"source sample rate",4000,96000)
    target=_integer(target_rate,"target sample rate",4000,96000)
    count=(len(data)*target+source-1)//source
    if count>32768:
        raise AudioKernelError("resampled PCM exceeds 32K sample budget")
    output=[]
    for i in range(count):
        index,fraction=divmod(i*source,target)
        if index>=len(data)-1:
            output.append(data[-1])
        else:
            value=(data[index]*(target-fraction)+data[index+1]*fraction+target//2)//target
            output.append(max(-32768,min(32767,value)))
    return tuple(output)
