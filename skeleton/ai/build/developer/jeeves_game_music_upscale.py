"""Real PCM16 soundtrack remaster and ambience layering for Jeeves GameForge.

Uses authored samples only. No fabricated music source, copyrighted third-
party stems, neural music generator or unverified quality certification.
"""
from __future__ import annotations

from hashlib import sha256
import io
from pathlib import Path, PurePosixPath
import struct
import wave
from typing import Any

from skeleton.developer.jeeves_game_authoring import _create_only
from skeleton.developer.jeeves_game_upscale import _policy

SCHEMA = "skeleton.jeeves.music_upscale.v1"
MAX_WAV_BYTES = 12 * 1024 * 1024


class MusicUpscaleError(ValueError):
    pass


def _audio_path(root:Path, path:str, *, must_exist:bool) -> Path:
    from skeleton.developer.game_cli import _load
    _load(root)
    if not isinstance(path,str) or not path.startswith("assets/") or "\\" in path or len(path)>256:
        raise MusicUpscaleError("audio must live under project assets/")
    parts=path.split("/")
    if len(parts)<2 or any(x in ("",".","..") for x in parts):
        raise MusicUpscaleError("unsafe audio path")
    if PurePosixPath(path).suffix.lower()!=".wav":
        raise MusicUpscaleError("audio enhancer currently requires PCM WAV")
    pos=root
    for seg in parts:
        pos=pos/seg
        if pos.is_symlink():
            raise MusicUpscaleError("audio path contains symlink")
    if must_exist and (not pos.is_file() or pos.stat().st_size>MAX_WAV_BYTES):
        raise MusicUpscaleError("source WAV missing or too large for one resampling slice")
    if not must_exist and pos.exists():
        raise MusicUpscaleError("audio output exists; never overwrite")
    return pos


def _decode(data:bytes) -> tuple[int,int,list[int]]:
    try:
        with wave.open(io.BytesIO(data),"rb") as f:
            if f.getcomptype()!="NONE" or f.getsampwidth()!=2 or f.getnchannels() not in (1,2):
                raise MusicUpscaleError("music needs uncompressed signed 16-bit mono/stereo WAV")
            rate=f.getframerate()
            if not 8000<=rate<=192000:
                raise MusicUpscaleError("unsupported WAV frame rate")
            frames=f.getnframes()
            if frames==0 or frames>3_000_000:
                raise MusicUpscaleError("empty or over-budget audio clip; split into resumable chunks")
            channels=f.getnchannels()
            payload=f.readframes(frames)
            if len(payload)!=frames*channels*2:
                raise MusicUpscaleError("truncated audio source")
            values=list(struct.unpack("<"+"h"*(frames*channels),payload))
            return rate,channels,values
    except (wave.Error,EOFError,struct.error) as exc:
        raise MusicUpscaleError("invalid PCM WAV file") from exc


def _pack(samples:list[int], rate:int, channels:int) -> bytes:
    encoded=struct.pack("<"+"h"*len(samples),*samples)
    buffer=io.BytesIO()
    with wave.open(buffer,"wb") as f:
        f.setnchannels(channels)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(encoded)
    return buffer.getvalue()


def remaster(root:Path, *, source:str, output:str, target:str,
             mode:str="remaster", ambience:str|None=None,
             dry_run:bool=False) -> dict[str,Any]:
    if mode not in ("remaster","ambience","cinematic"):
        raise MusicUpscaleError("invalid music upscale mode")
    if mode=="ambience" and not ambience:
        raise MusicUpscaleError("ambience mode requires a separate original stem")
    policy=_policy(target)
    src=_audio_path(root,source,must_exist=True)
    dest=_audio_path(root,output,must_exist=False)
    if src==dest:
        raise MusicUpscaleError("cannot overwrite source music")
    raw=src.read_bytes()
    rate,channels,samples=_decode(raw)
    stem=None
    stem_digest=None
    if ambience is not None:
        stem_raw=_audio_path(root,ambience,must_exist=True).read_bytes()
        rate2,channels2,stem=_decode(stem_raw)
        if rate2!=rate or channels2!=channels:
            raise MusicUpscaleError("ambience stem must share source rate and channel count")
        stem_digest=sha256(stem_raw).hexdigest()
    peak=max(abs(v) for v in samples)
    if not peak:
        raise MusicUpscaleError("silent original audio cannot be scored or remastered")
    headroom=0.84 if mode=="cinematic" else 0.89
    gain=min(3.0,32767*headroom/peak)
    # Bounded linear gain plus a subtle source-derived echo. This never
    # changes notes/motif or generates an independent melody.
    delayed=(rate*channels)//8
    out=[]
    max_abs=0
    for i,v in enumerate(samples):
        sample=v*gain
        if mode in ("ambience","cinematic") and i>=delayed:
            sample+=samples[i-delayed]*gain*(0.13 if mode=="cinematic" else 0.07)
        if stem is not None:
            sample+=stem[i%len(stem)]*0.12
        quantized=max(-32768,min(32767,round(sample)))
        max_abs=max(max_abs,abs(quantized))
        out.append(quantized)
    blob=_pack(out,rate,channels)
    result={
        "ok":True,"action":"upscale-music","schema":SCHEMA,
        "target":policy["target_id"],"mode":mode,
        "source":source,"output":output,
        "source_sha256":sha256(raw).hexdigest(),
        "output_sha256":sha256(blob).hexdigest(),
        "ambience_stem_sha256":stem_digest,
        "channels":channels,"sample_rate":rate,
        "source_frames":len(samples)//channels,
        "output_frames":len(out)//channels,
        "measured_source_peak":peak,
        "measured_output_peak":max_abs,
        "preserves_sample_count_and_tempo":True,
        "music_quality_independently_reviewed":False,
        "audio_listening_test_performed":False,
        "dry_run":dry_run,
    }
    if not dry_run:
        _create_only(dest,blob)
        from skeleton.developer.jeeves_game_upscale_queue import record_output
        result["training_candidate"]=record_output(
            root,category="music",source=source,output=output,
            input_sha256=result["source_sha256"],output_sha256=result["output_sha256"],
            target=policy["target_id"],quality="requires_review")
    return result
