"""Homebrew adaptive music stem mixer with real stereo PCM audio output.

Builds a single source-bound WAV from individually rendered authored scores,
with normalized weights and sample-by-sample bounded envelope transitions.
No sampling of licensed music and no reliance on an external codec.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import struct
import wave
from math import isfinite

from .game_frontier_expedition import ExpeditionError,_digest
from .game_frontier_expedition_audio import (
    AudioScore,MusicalNote,render_original_audio,
)

@dataclass(frozen=True,slots=True)
class AudioStem:
    score:AudioScore
    weight:float
    final_weight:float

    def __post_init__(self):
        if not isinstance(self.score,AudioScore):
            raise ExpeditionError("audio stem requires original score")
        for val in (self.weight,self.final_weight):
            if type(val) not in (int,float) or not isfinite(val) or not 0<=val<=1:
                raise ExpeditionError("adaptive audio mix gain invalid")


def mix_original_stems(stems:tuple[AudioStem,...])->dict:
    if (type(stems) is not tuple or not 1<=len(stems)<=8
            or any(not isinstance(stem,AudioStem) for stem in stems)):
        raise ExpeditionError("audio mixer expects 1..8 real authored stems")
    source=stems[0].score
    if any(stem.score.world_digest!=source.world_digest
           or stem.score.sample_rate!=source.sample_rate
           or stem.score.duration_ms!=source.duration_ms for stem in stems):
        raise ExpeditionError("adaptive audio stems must belong to one original game/clock")
    if sum(x.weight for x in stems)>2 or sum(x.final_weight for x in stems)>2:
        raise ExpeditionError("audio gain sum above clipping prevention bound")
    chunks=[]
    for stem in stems:
        raw=render_original_audio(stem.score)
        with wave.open(BytesIO(raw),"rb") as wav:
            if wav.getnchannels()!=1 or wav.getsampwidth()!=2 or wav.getframerate()!=source.sample_rate:
                raise ExpeditionError("original audio stem format is foreign")
            chunks.append(wav.readframes(wav.getnframes()))
    frames=len(chunks[0])//2
    if frames<=0 or any(len(b)!=len(chunks[0]) for b in chunks):
        raise ExpeditionError("audio stem sizes do not match")
    output=bytearray(frames*2)
    peak=0
    for i in range(frames):
        progress=i/max(1,frames-1)
        value=0.
        for stem,chunk in zip(stems,chunks):
            sample=struct.unpack_from("<h",chunk,i*2)[0]
            gain=stem.weight*(1-progress)+stem.final_weight*progress
            value+=sample*gain
        clamped=max(-32768,min(32767,round(value)))
        peak=max(peak,abs(clamped))
        struct.pack_into("<h",output,i*2,clamped)
    stream=BytesIO()
    with wave.open(stream,"wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(source.sample_rate)
        writer.writeframes(output)
    raw=stream.getvalue()
    report={
        "schema":"skeleton.game.original_adaptive_audio.v1",
        "world_digest":source.world_digest,
        "stem_sources":[x.score.digest for x in stems],
        "stems":len(stems),
        "start_gains":[x.weight for x in stems],
        "end_gains":[x.final_weight for x in stems],
        "sample_rate":source.sample_rate,
        "samples_mixed":frames,
        "clamped_peak":peak,
        "audio_sha256":sha256(raw).hexdigest(),
        "algorithm":"bounded_linear_crossfade_pcm16",
        "native_playback_verified":False,
    }
    report["receipt_digest"]=_digest(report)
    return {"wav":raw,"manifest":report}


def verify_original_mix(stems:tuple[AudioStem,...],mixed:dict)->None:
    if not isinstance(mixed,dict) or mixed!=mix_original_stems(stems):
        raise ExpeditionError("original adaptive audio differs from source stems")


def make_original_ambient_layers(score:AudioScore)->tuple[AudioStem,...]:
    if not isinstance(score,AudioScore):
        raise ExpeditionError("original score required for adaptive music")
    from dataclasses import replace
    melody=replace(score,ambience="none")
    atmosphere=replace(score,notes=(),ambience="wind",environment_strength=.8)
    if score.ambience in ("rain","forest","cave","volcano","underwater"):
        secondary=replace(score,notes=(),environment_strength=.85)
    else:
        secondary=replace(score,notes=(),ambience="rain",environment_strength=.4)
    return (
        AudioStem(melody,.9,.6),
        AudioStem(atmosphere,.1,.35),
        AudioStem(secondary,0.,.45),
    )
