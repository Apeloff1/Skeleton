"""Chunked consent checkpoints for long Dragon temporal traces."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256

from .dragon_consent_bound_queue import ConsentBoundAnalysisQueue
from .dragon_temporal_segmentation import FeatureFrame,SegmentationConfig,TemporalEvent,segment_feature_trace

@dataclass(frozen=True)
class ChunkedTemporalTrace:
    events:tuple[TemporalEvent,...]
    chunks_checked:int
    trace_fingerprint:str

def segment_with_consent_checkpoints(custody:ConsentBoundAnalysisQueue,owner:str,job_id:str,
    frames:tuple[FeatureFrame,...],*,now:float,authorized:bool,chunk_size:int=512,
    config:SegmentationConfig=SegmentationConfig())->ChunkedTemporalTrace:
    if not authorized: raise PermissionError("chunked temporal analysis requires authorization")
    if not 2<=chunk_size<=10000: raise ValueError("invalid temporal chunk size")
    if not frames: return ChunkedTemporalTrace((),0,sha256(b"").hexdigest())
    # overlap retains boundary transitions; event de-duplication is structural.
    events=[];seen=set();checks=0
    for start in range(0,len(frames),chunk_size):
        custody.require_active(owner,job_id,now=now,authorized=True);checks+=1
        lo=max(0,start-1); hi=min(len(frames),start+chunk_size)
        chunk=frames[lo:hi]
        if len(chunk)<2: continue
        local=segment_feature_trace(chunk,authorized=True,config=config)
        for event in local:
            key=(event.start_ms,event.peak_ms,event.end_ms,event.source_frame_ids)
            if key not in seen: seen.add(key);events.append(event)
    custody.require_active(owner,job_id,now=now,authorized=True);checks+=1
    events.sort(key=lambda x:(x.start_ms,x.peak_ms,x.end_ms,x.source_frame_ids))
    fp=sha256("\n".join(
        f"{e.start_ms}:{e.peak_ms}:{e.end_ms}:{','.join(e.source_frame_ids)}"
        for e in events).encode()).hexdigest()
    return ChunkedTemporalTrace(tuple(events),checks,fp)
