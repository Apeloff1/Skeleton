"""Original offline PCM synth for authenticated rhythm beat charts.

No soundfonts, recordings, borrowed score, external synthesizer executable,
network, runtime downloads, plugins, JS execution or copyrighted game audio.
Deterministic bounded PCM, automatically compatible with WAV playback.
"""
from __future__ import annotations

from io import BytesIO
from hashlib import sha256
import math
import struct
import wave

from .advanced_rhythm_runtime import normalize_layout

SAMPLE_RATE=12000
MAX_RENDER_MS=20000
MAX_SYNTH_NOTES=256


class RhythmAudioError(ValueError):
    """Unsafe or incoherent original beat-chart synthesis request."""


def _waveform(phase,instrument):
    phase%=1.0
    if instrument=="original_sine":
        return math.sin(phase*2*math.pi)
    if instrument=="original_triangle":
        return 4*abs(phase-0.5)-1
    if instrument=="original_pulse":
        return 1.0 if phase<0.25 else -1.0
    return 0.0


def render_original_beat_wav(layout,config,*,from_ms=0,duration_ms=10000):
    """Synthesize an original chart section to a 12kHz mono 16-bit WAV.

    Audio render is bounded to 20 sec and 256 chart notes. From_ms allows
    creating any non-overlapping preview section for long 256-beat songs,
    without ever treating one 20s preview as the entire soundtrack.
    """
    chart=normalize_layout(config,layout)
    if type(from_ms) is not int or not 0<=from_ms<=600000:
        raise RhythmAudioError("original preview offset must be bounded integer milliseconds")
    if type(duration_ms) is not int or not 50<=duration_ms<=MAX_RENDER_MS:
        raise RhythmAudioError("original PCM window must be 50..20000 ms")
    if len(chart["notes"])>MAX_SYNTH_NOTES:
        raise RhythmAudioError("original song exceeds admitted source note count")
    if config["instrument"] not in (
        "original_sine","original_triangle","original_pulse","silent"):
        raise RhythmAudioError("unregistered original oscillator")
    size=duration_ms*SAMPLE_RATE//1000
    active_notes=[
      n for n in chart["notes"] if
      (n["at"]+chart["offset_ms"]<from_ms+duration_ms and
       n["at"]+chart["offset_ms"]+
       max(n["duration"],100) >=from_ms)
    ]
    # Precompute note frequency and length; no external recordings.
    primitives=[]
    for n in active_notes:
        onset=n["at"]+chart["offset_ms"]
        dur=max(125,min(1800,n["duration"] if n["kind"]=="hold" else 200))
        freq=196.0*2**((n["lane"]*2+int(n["accent"])*3)/12)
        if n["kind"]=="mine":freq*=0.5
        amplitude=(config["note_velocity"]/127.0)*(0.7 if
                   n["kind"]=="mine" else 1.0)
        voices=[freq]
        if n["kind"]=="chord" and n["partner"] is not None:
            voices.append(196.0*2**((n["partner"]*2+3)/12))
        primitives.append((onset,dur,voices,amplitude))
    samples=bytearray(size*2)
    if not config["sound_enabled"] or config["instrument"]=="silent":
        # A valid original sound-disabled WAV has exact-length silence.
        with BytesIO() as io:
            with wave.open(io,"wb") as writer:
                writer.setnchannels(1);writer.setsampwidth(2)
                writer.setframerate(SAMPLE_RATE)
                writer.writeframes(samples)
            return io.getvalue()
    # Fixed-point time positions avoid tick-order dependent synthesis.
    for j in range(size):
        ms=from_ms+j*1000.0/SAMPLE_RATE
        mix=0.0
        for at,dur,voices,amp in primitives:
            elapsed=ms-at
            if not 0<=elapsed<dur:continue
            envelope=min(1.0,elapsed/12.0)*max(0.0,1.0-elapsed/dur)
            strength=amp*envelope/len(voices)
            for frequency in voices:
                mix+=strength*_waveform(elapsed*frequency/1000,
                                        config["instrument"])
        samples[j*2:j*2+2]=struct.pack(
            "<h",max(-32767,min(32767,round(12000*math.tanh(mix)))))
    with BytesIO() as io:
        with wave.open(io,"wb") as writer:
            writer.setnchannels(1);writer.setsampwidth(2)
            writer.setframerate(SAMPLE_RATE)
            writer.writeframes(samples)
        return io.getvalue()


def original_audio_receipt(layout,config,*,from_ms=0,duration_ms=10000):
    from .advanced_rhythm_runtime import normalize_layout
    chart=normalize_layout(config,layout)
    sound=render_original_beat_wav(chart,config,from_ms=from_ms,
                                   duration_ms=duration_ms)
    return {
        "schema":"skeleton.game_builder.original_rhythm_audio.v1",
        "audio_format":"wav_pcm_s16le_mono","rate_hz":SAMPLE_RATE,
        "renderer":"original_math_oscillator_no_third_party_samples",
        "original_instrument":config["instrument"],
        "original_sound_enabled":config["sound_enabled"],
        "window_start_ms":from_ms,"window_duration_ms":duration_ms,
        "bytes":len(sound),"sha256":sha256(sound).hexdigest(),
        "native_playback_certified":False,
        "original_audio_asset_required":False,
    }


__all__=["SAMPLE_RATE","MAX_RENDER_MS","RhythmAudioError",
         "render_original_beat_wav","original_audio_receipt"]
