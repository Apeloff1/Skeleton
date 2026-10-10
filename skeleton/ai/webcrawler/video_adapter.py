"""Adapter-neutral video ingestion with explicit consent and provenance."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable,Protocol
from .video_digest import VideoObservation,VideoKnowledgeChunk
from .video_stream import VideoStreamSession

@dataclass(frozen=True)
class VideoSourceGrant:
    source_url:str
    authorized:bool
    allow_transcript:bool=True
    allow_visual:bool=False
    allow_audio:bool=False
    max_observations:int=1000

@dataclass(frozen=True)
class VideoAdapterFrame:
    start_ms:int
    end_ms:int
    modality:str
    description:str
    confidence:float
    origin_id:str

class VideoObservationAdapter(Protocol):
    def observations(self,source_url:str)->Iterable[VideoAdapterFrame]: ...

def ingest_authorized_video(grant:VideoSourceGrant,adapter:VideoObservationAdapter, *,
                            window_ms:int=30000)->tuple[VideoKnowledgeChunk,...]:
    if not grant.authorized:raise PermissionError("video ingestion requires explicit authorization")
    if not 1<=grant.max_observations<=100000:raise ValueError("invalid observation budget")
    session=VideoStreamSession(grant.source_url,window_ms=window_ms,max_observations=grant.max_observations)
    result=[]
    for frame in adapter.observations(grant.source_url):
        if frame.modality in ("transcript","caption") and not grant.allow_transcript:raise PermissionError("transcript processing not authorized")
        if frame.modality in ("frame_description","ocr") and not grant.allow_visual:raise PermissionError("visual processing not authorized")
        if frame.modality=="audio_description" and not grant.allow_audio:raise PermissionError("audio processing not authorized")
        session.push(VideoObservation(frame.start_ms,frame.end_ms,frame.modality,frame.description,frame.confidence,
                                      sha256((grant.source_url+":"+frame.origin_id).encode()).hexdigest()))
        result.extend(session.flush_ready())
    result.extend(session.close())
    return tuple(result)
