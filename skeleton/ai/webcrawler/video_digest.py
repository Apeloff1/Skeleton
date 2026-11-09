"""Bounded time-coded video observations for the dragon knowledge pipeline.

This module accepts decoded transcript/visual observations from an authorized media
adapter. It does not bypass DRM, download streams, or claim to decode pixels.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Iterable

@dataclass(frozen=True)
class VideoObservation:
    start_ms:int
    end_ms:int
    modality:str
    text:str
    confidence:float
    source_id:str

@dataclass(frozen=True)
class VideoKnowledgeChunk:
    chunk_id:str
    start_ms:int
    end_ms:int
    text:str
    modalities:tuple[str,...]
    observation_ids:tuple[str,...]
    source_url:str

def validate_observation(o:VideoObservation)->None:
    if o.modality not in ("transcript","caption","frame_description","audio_description","ocr"):
        raise ValueError("unsupported modality")
    if not 0<=o.start_ms<o.end_ms<=86_400_000 or o.end_ms-o.start_ms>300_000:
        raise ValueError("invalid observation interval")
    if not math.isfinite(o.confidence) or not 0<=o.confidence<=1:
        raise ValueError("invalid confidence")
    if not o.source_id or len(o.source_id)>256 or not o.text.strip() or len(o.text)>10_000:
        raise ValueError("invalid observation evidence")

def digest_video_observations(source_url:str, observations:Iterable[VideoObservation], *,
                              window_ms:int=30_000,max_observations:int=10_000)->tuple[VideoKnowledgeChunk,...]:
    if not source_url.startswith(("https://","http://")) or len(source_url)>4096:
        raise ValueError("invalid video source")
    if not 1000<=window_ms<=300_000 or not 1<=max_observations<=100_000:
        raise ValueError("invalid digestion limits")
    items=[]
    for observation in observations:
        if len(items)>=max_observations:
            raise ValueError("video observation budget exhausted")
        validate_observation(observation)
        items.append(observation)
    items.sort(key=lambda o:(o.start_ms,o.end_ms,o.modality,o.source_id,o.text))
    groups:dict[int,list[VideoObservation]]={}
    for o in items:
        groups.setdefault(o.start_ms//window_ms,[]).append(o)
    result=[]
    for bucket,group in sorted(groups.items()):
        start=min(x.start_ms for x in group)
        end=max(x.end_ms for x in group)
        evidence=[{"start_ms":x.start_ms,"end_ms":x.end_ms,"modality":x.modality,
                   "text":x.text,"confidence":x.confidence,"source_id":x.source_id} for x in group]
        canonical=json.dumps({"source":source_url,"bucket":bucket,"evidence":evidence},
                             sort_keys=True,separators=(",",":"),ensure_ascii=False)
        chunk_id=sha256(canonical.encode()).hexdigest()
        text="\n".join(f"[{x.start_ms/1000:.2f}-{x.end_ms/1000:.2f}s | {x.modality} | confidence={x.confidence:.2f}] {x.text}" for x in group)
        result.append(VideoKnowledgeChunk(chunk_id,start,end,text,tuple(sorted({x.modality for x in group})),
                                          tuple(x.source_id for x in group),source_url))
    return tuple(result)
