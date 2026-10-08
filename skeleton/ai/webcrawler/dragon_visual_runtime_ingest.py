"""Transactional ingestion of browser visual evidence into Dragon runtime."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json

from .dragon_analysis_chains import AnalysisLayer,LayerReceipt
from .dragon_analysis_runtime import DragonAnalysisRuntime,RunCheckpoint
from .dragon_browser_visual_import import BrowserVisualEnvelope,accept_browser_visual
from .dragon_consent_bound_queue import ConsentBoundAnalysisQueue
from .dragon_motion_features import derive_motion_features
from .dragon_chunked_temporal import segment_with_consent_checkpoints

@dataclass(frozen=True)
class VisualRuntimeIngest:
    source_receipt:LayerReceipt
    temporal_receipt:LayerReceipt
    checkpoint:RunCheckpoint
    event_count:int

def _digest(value:object)->str:
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def ingest_browser_visual(runtime:DragonAnalysisRuntime,custody:ConsentBoundAnalysisQueue,
    envelope:BrowserVisualEnvelope,run_id:str,*,now:float,authorized:bool,
    chunk_size:int=512)->VisualRuntimeIngest:
    if not authorized: raise PermissionError("visual runtime ingestion requires authorization")
    cp=runtime.checkpoint(envelope.owner,run_id,authorized=True)
    if cp.cancelled or cp.state!="running": raise PermissionError("analysis run is not active")
    accepted=accept_browser_visual(custody,envelope,now=now,authorized=True)
    source=LayerReceipt(AnalysisLayer.SOURCE_INTEGRITY,(),accepted.envelope_fingerprint,1,True)
    cp=runtime.commit_receipt(envelope.owner,run_id,source,now=now,
        expected_revision=cp.revision,authorized=True)
    # Consent is checked inside the chunk worker before each bounded slice.
    motion=derive_motion_features(accepted.features,authorized=True)
    trace=segment_with_consent_checkpoints(custody,envelope.owner,envelope.job_id,
        motion.frames,now=now,authorized=True,chunk_size=chunk_size)
    temporal_fp=_digest({"source":source.output_fingerprint,
      "motion":motion.motion_fingerprint,"trace":trace.trace_fingerprint,
      "events":[[e.start_ms,e.peak_ms,e.end_ms,e.source_frame_ids] for e in trace.events]})
    temporal=LayerReceipt(AnalysisLayer.TEMPORAL_SEGMENTATION,
        (source.output_fingerprint,),temporal_fp,1,True)
    cp=runtime.commit_receipt(envelope.owner,run_id,temporal,now=now,
        expected_revision=cp.revision,authorized=True)
    return VisualRuntimeIngest(source,temporal,cp,len(trace.events))
