"""Deterministic homebrew game music and ambient audio as playable PCM/WAV.

Generates actual mono 16-bit RIFF WAVE clips from explicitly authored notes
and environment synthesis; no sound recordings or licensed music are sampled.
Bounded render budgets prevent accidental resource exhaustion.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
from math import sin, pi, tanh, isfinite
from io import BytesIO
import struct
import wave

from .game_frontier_expedition import ExpeditionError, ExpeditionWorld, _digest

SCHEMA="skeleton.game.original_audio.v1"


@dataclass(frozen=True, slots=True)
class MusicalNote:
    frequency_hz: float
    start_ms: int
    length_ms: int
    volume: float = 0.25
    instrument: str = "sine"

    def __post_init__(self):
        if type(self.frequency_hz) not in (int,float) or not isfinite(self.frequency_hz) or not 30 <= self.frequency_hz <= 12000:
            raise ExpeditionError("original tone frequency not playable")
        if (type(self.start_ms) is not int or not 0 <= self.start_ms <= 30000
                or type(self.length_ms) is not int or not 10 <= self.length_ms <= 30000):
            raise ExpeditionError("original note timing exceeds safe clip length")
        if type(self.volume) not in (int,float) or not isfinite(self.volume) or not 0 <= self.volume <= 1:
            raise ExpeditionError("original sound level is nonfinite")
        if self.instrument not in {"sine","organ","bell","reed","flute"}:
            raise ExpeditionError("unknown homebrew oscillator instrument")


@dataclass(frozen=True,slots=True)
class AudioScore:
    score_id: str
    world_digest: str
    notes: tuple[MusicalNote, ...]
    duration_ms: int = 4000
    sample_rate: int = 16000
    ambience: str = "none"
    environment_strength: float = 0.2

    def __post_init__(self):
        if not isinstance(self.score_id,str) or not self.score_id.isidentifier():
            raise ExpeditionError("original music requires score identity")
        if type(self.world_digest) is not str or len(self.world_digest)!=64:
            raise ExpeditionError("game audio needs source-bound world")
        if type(self.duration_ms) is not int or not 100<=self.duration_ms<=30000:
            raise ExpeditionError("audio clip duration must be bounded")
        if type(self.sample_rate) is not int or self.sample_rate not in (8000,16000,22050,44100):
            raise ExpeditionError("audio sample rate not supported")
        if type(self.notes) is not tuple or len(self.notes)>128:
            raise ExpeditionError("original music notes must be finite")
        if self.ambience not in {"none","wind","rain","cave","underwater","forest","volcano"}:
            raise ExpeditionError("unknown environmental soundscape")
        if (type(self.environment_strength) not in (int,float) or
                not isfinite(self.environment_strength) or
                not 0<=self.environment_strength<=1):
            raise ExpeditionError("ambience strength must be finite")
        if any(note.start_ms+note.length_ms>self.duration_ms for note in self.notes):
            raise ExpeditionError("original audio score contains truncated note")

    @property
    def digest(self):
        return _digest({"schema":SCHEMA,"score":self.score_id,
                        "world":self.world_digest,
                        "notes":[asdict(n) for n in self.notes],
                        "duration_ms":self.duration_ms,"rate":self.sample_rate,
                        "ambience":self.ambience,
                        "strength":self.environment_strength})


def _tone(note:MusicalNote,t:float)->float:
    phase=2*pi*note.frequency_hz*t
    if note.instrument=="organ":
        value=0.58*sin(phase)+0.22*sin(2*phase)+0.12*sin(3*phase)
    elif note.instrument=="bell":
        value=0.7*sin(phase)+0.25*sin(2.013*phase)+0.12*sin(3.921*phase)
    elif note.instrument=="reed":
        value=tanh(1.4*sin(phase)+0.25*sin(3*phase))
    elif note.instrument=="flute":
        value=0.88*sin(phase)+0.07*sin(2*phase)
    else:
        value=sin(phase)
    attack=min(1,t/.012)
    release=min(1,(note.length_ms/1000-t)/.08)
    return value*note.volume*max(0,min(attack,release))


def _noise(tick:int,seed:int)->float:
    # Reproducible integer PRNG, never the Python process-randomized hash.
    value=(tick*0x9e3779b1+seed*0x85ebca6b)&0xffffffff
    value^=value>>16
    value=(value*0x7feb352d)&0xffffffff
    value^=value>>15
    return ((value&65535)/32767.5)-1


def render_original_audio(score:AudioScore)->bytes:
    if not isinstance(score,AudioScore):
        raise ExpeditionError("typed authored music score required")
    count=score.duration_ms*score.sample_rate//1000
    if count>1_323_000:
        raise ExpeditionError("music sample budget exhausted")
    seed=int(score.world_digest[:8],16)
    pcm=bytearray(count*2)
    for i in range(count):
        t=i/score.sample_rate
        mixed=0.
        for note in score.notes:
            start=note.start_ms/1000
            if start<=t<(note.start_ms+note.length_ms)/1000:
                mixed+=_tone(note,t-start)
        if score.ambience!="none":
            noise=_noise(i//3,seed)
            if score.ambience=="rain":
                ambient=noise*0.25+abs(_noise(i//49,seed))*0.12
            elif score.ambience=="wind":
                ambient=noise*(0.09+0.12*(sin(t*1.3)**2))
            elif score.ambience=="underwater":
                ambient=0.3*sin(t*45)+0.04*noise
            elif score.ambience=="cave":
                ambient=0.2*sin(t*52)+0.12*sin(t*54)
            elif score.ambience=="forest":
                ambient=0.10*sin(t*1300+sin(t*4))+0.09*noise
            elif score.ambience=="volcano":
                ambient=0.24*sin(t*41)+0.21*noise
            else:
                ambient=0.08*noise
            mixed+=score.environment_strength*ambient
        mixed=tanh(mixed*1.6)*0.78
        sample=max(-32768,min(32767,round(mixed*32767)))
        struct.pack_into("<h",pcm,i*2,sample)
    out=BytesIO()
    with wave.open(out,"wb") as container:
        container.setnchannels(1)
        container.setsampwidth(2)
        container.setframerate(score.sample_rate)
        container.writeframes(pcm)
    return out.getvalue()


def original_world_score(world:ExpeditionWorld, *, ambience:str="wind",
                         seconds:int=3)->AudioScore:
    if not isinstance(world,ExpeditionWorld) or type(seconds) is not int or not 1<=seconds<=30:
        raise ExpeditionError("soundscape requires an authored bounded game")
    base=165+int(world.digest[:4],16)%90
    pattern=(0,3,7,5,10,7,3,0)
    beat=seconds*1000//8
    notes=tuple(MusicalNote(
        frequency_hz=base*2**(step/12),start_ms=index*beat,
        length_ms=min(beat*2,seconds*1000-index*beat),
        volume=.21,instrument=("flute" if index%2 else "bell")
    ) for index,step in enumerate(pattern))
    return AudioScore("original_sky_motif",world.digest,notes,
                      duration_ms=seconds*1000,ambience=ambience)


def export_original_soundscape(world:ExpeditionWorld, *, ambience:str="wind",
                               seconds:int=3)->dict:
    score=original_world_score(world,ambience=ambience,seconds=seconds)
    pcm=render_original_audio(score)
    manifest={
        "schema":SCHEMA,"world_digest":world.digest,
        "source_digest":world.source_digest,"score_digest":score.digest,
        "duration_ms":score.duration_ms,"sample_rate":score.sample_rate,
        "ambience":score.ambience,"notes":len(score.notes),
        "audio_sha256":sha256(pcm).hexdigest(),
        "audio_bytes":len(pcm),"copyright_sampling_used":False,
        "native_audio_playback_verified":False,
    }
    manifest["receipt_digest"]=_digest(manifest)
    return {"score":score,"wav":pcm,"manifest":manifest}


def verify_original_soundscape(world:ExpeditionWorld,bundle:dict, *,
                               ambience:str="wind",seconds:int=3)->None:
    expected=export_original_soundscape(world,ambience=ambience,seconds=seconds)
    if (not isinstance(bundle,dict) or set(bundle)!=set(expected)
            or bundle["wav"]!=expected["wav"]
            or bundle["score"]!=expected["score"]
            or bundle["manifest"]!=expected["manifest"]):
        raise ExpeditionError("audio does not reproduce against original world")
