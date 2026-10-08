"""Chunk-invariant temporal segmentation with bounded consent checkpoints."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json

from .dragon_temporal_segmentation import FeatureFrame,TemporalEvent,SegmentationConfig,segment_feature_trace
from .dragon_consent_bound_queue import ConsentBoundAnalysisQueue

@dataclass(frozen=True)
class StreamingTemporalTrace:
 events:tuple[TemporalEvent,...]; checkpoints:int; trace_fingerprint:str

def segment_streaming_with_consent(custody:ConsentBoundAnalysisQueue,owner:str,job_id:str,
 frames:tuple[FeatureFrame,...],*,now:float,authorized:bool,checkpoint_frames:int=256,
 config:SegmentationConfig=SegmentationConfig())->StreamingTemporalTrace:
 if not authorized:raise PermissionError("streaming temporal analysis requires authorization")
 if not 2<=checkpoint_frames<=10000:raise ValueError("invalid checkpoint frame budget")
 if len(frames)>config.max_frames:raise ValueError("frame budget exceeded")
 # Validate consent repeatedly while preserving one canonical segmentation state.
 checkpoints=0
 for start in range(0,max(1,len(frames)),checkpoint_frames):
  custody.require_active(owner,job_id,now=now,authorized=True);checkpoints+=1
 # Segmentation runs exactly once over the canonical ordered trace. Chunk size therefore
 # controls cancellation/consent polling only and cannot alter event boundaries.
 events=segment_feature_trace(frames,authorized=True,config=config)
 custody.require_active(owner,job_id,now=now,authorized=True);checkpoints+=1
 fp=sha256(json.dumps({"frames":[[f.timestamp_ms,f.features,f.source_frame_id] for f in frames],
  "events":[[e.start_ms,e.peak_ms,e.end_ms,e.peak_change,e.baseline_change,
   e.feature_indices,e.source_frame_ids] for e in events],"config":vars(config)},
  sort_keys=True,separators=(",",":")).encode()).hexdigest()
 return StreamingTemporalTrace(events,checkpoints,fp)
