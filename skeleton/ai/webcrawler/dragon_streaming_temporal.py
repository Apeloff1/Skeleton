"""Chunk-invariant temporal segmentation with bounded consent checkpoints."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json,time
from typing import Callable

from .dragon_temporal_segmentation import FeatureFrame,TemporalEvent,SegmentationConfig,segment_feature_trace
from .dragon_consent_bound_queue import ConsentBoundAnalysisQueue

@dataclass(frozen=True)
class StreamingTemporalTrace:
 events:tuple[TemporalEvent,...]; checkpoints:int; trace_fingerprint:str

def segment_streaming_with_consent(custody:ConsentBoundAnalysisQueue,owner:str,job_id:str,
 frames:tuple[FeatureFrame,...],*,now:float|None=None,clock:Callable[[],float]|None=None,
 authorized:bool,checkpoint_frames:int=256,
 config:SegmentationConfig=SegmentationConfig())->StreamingTemporalTrace:
 if not authorized:raise PermissionError("streaming temporal analysis requires authorization")
 if not 2<=checkpoint_frames<=10000:raise ValueError("invalid checkpoint frame budget")
 if len(frames)>config.max_frames:raise ValueError("frame budget exceeded")
 # Every checkpoint obtains fresh time. Explicit now remains a deterministic compatibility clock.
 if clock is not None and now is not None:raise ValueError("provide clock or now, not both")
 read_clock=clock or ((lambda: now) if now is not None else time.time)
 checkpoints=0;last_now=None
 def checkpoint():
  nonlocal checkpoints,last_now
  current=read_clock()
  if not isinstance(current,(int,float)) or not __import__("math").isfinite(current):raise ValueError("invalid checkpoint clock")
  if last_now is not None and current<last_now:raise RuntimeError("checkpoint clock regressed")
  custody.require_active(owner,job_id,now=current,authorized=True);last_now=current;checkpoints+=1
 for start in range(0,max(1,len(frames)),checkpoint_frames):
  checkpoint()
 # Segmentation runs exactly once over the canonical ordered trace. Chunk size therefore
 # controls cancellation/consent polling only and cannot alter event boundaries.
 events=segment_feature_trace(frames,authorized=True,config=config)
 checkpoint()
 fp=sha256(json.dumps({"frames":[[f.timestamp_ms,f.features,f.source_frame_id] for f in frames],
  "events":[[e.start_ms,e.peak_ms,e.end_ms,e.peak_change,e.baseline_change,
   e.feature_indices,e.source_frame_ids] for e in events],"config":vars(config)},
  sort_keys=True,separators=(",",":")).encode()).hexdigest()
 return StreamingTemporalTrace(events,checkpoints,fp)
