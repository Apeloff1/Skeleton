"""Transactional ingestion of browser visual evidence into Dragon runtime."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json,math,time
from typing import Callable

from .dragon_analysis_chains import AnalysisLayer,LayerReceipt
from .dragon_analysis_runtime import DragonAnalysisRuntime,RunCheckpoint
from .dragon_browser_visual_import import BrowserVisualEnvelope,accept_browser_visual
from .dragon_consent_bound_queue import ConsentBoundAnalysisQueue
from .dragon_motion_features import derive_motion_features
from .dragon_streaming_temporal import segment_streaming_with_consent
from .dragon_runtime_events import DragonRuntimeEventLedger

@dataclass(frozen=True)
class VisualRuntimeIngest:
    source_receipt:LayerReceipt
    temporal_receipt:LayerReceipt
    checkpoint:RunCheckpoint
    event_count:int

def _digest(value:object)->str:
    return sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def _commit_stage(runtime:DragonAnalysisRuntime,ledger:DragonRuntimeEventLedger,
    owner:str,run_id:str,receipt:LayerReceipt,*,now:float,
    expected_revision:int)->RunCheckpoint:
    with runtime.db:
        cp=runtime._commit_receipt_uncommitted(owner,run_id,receipt,now=now,
            expected_revision=expected_revision,authorized=True)
        ledger._append_uncommitted(owner,run_id,event_type="receipt",
            layer=receipt.layer.value,outcome="accepted",
            evidence_fingerprint=receipt.output_fingerprint,error_code="",
            occurred_at=now,authorized=True)
        return cp

def ingest_browser_visual(runtime:DragonAnalysisRuntime,custody:ConsentBoundAnalysisQueue,
    envelope:BrowserVisualEnvelope,run_id:str,*,now:float,authorized:bool,
    chunk_size:int=512,clock:Callable[[],float]=time.time)->VisualRuntimeIngest:
    if not authorized: raise PermissionError("visual runtime ingestion requires authorization")
    cp=runtime.checkpoint(envelope.owner,run_id,authorized=True)
    if cp.cancelled or cp.state!="running": raise PermissionError("analysis run is not active")
    ledger=DragonRuntimeEventLedger(runtime.db)
    consent_now=clock()
    if isinstance(consent_now,bool) or not isinstance(consent_now,(int,float)) or not math.isfinite(consent_now):
        raise ValueError("invalid visual ingestion clock")
    ledger.append(envelope.owner,run_id,event_type="attempt",layer="source_integrity",outcome="started",occurred_at=now,authorized=True)
    try:
        accepted=accept_browser_visual(custody,envelope,now=float(consent_now),authorized=True)
    except Exception as exc:
        ledger.append(envelope.owner,run_id,event_type="attempt",layer="source_integrity",outcome="failed",error_code=type(exc).__name__,occurred_at=now,authorized=True)
        raise
    source=LayerReceipt(AnalysisLayer.SOURCE_INTEGRITY,(),accepted.envelope_fingerprint,1,True)
    cp=_commit_stage(runtime,ledger,envelope.owner,run_id,source,now=now,
        expected_revision=cp.revision)
    # Consent is checked inside the chunk worker before each bounded slice.
    ledger.append(envelope.owner,run_id,event_type="attempt",layer="temporal_segmentation",outcome="started",evidence_fingerprint=source.output_fingerprint,occurred_at=now,authorized=True)
    try:
        motion=derive_motion_features(accepted.features,authorized=True)
        trace=segment_streaming_with_consent(custody,envelope.owner,envelope.job_id,
            motion.frames,clock=clock,authorized=True,checkpoint_frames=chunk_size)
    except Exception as exc:
        ledger.append(envelope.owner,run_id,event_type="attempt",layer="temporal_segmentation",outcome="failed",evidence_fingerprint=source.output_fingerprint,error_code=type(exc).__name__,occurred_at=now,authorized=True)
        raise
    temporal_fp=_digest({"source":source.output_fingerprint,
      "motion":motion.motion_fingerprint,"trace":trace.trace_fingerprint,
      "events":[[e.start_ms,e.peak_ms,e.end_ms,e.source_frame_ids] for e in trace.events]})
    temporal=LayerReceipt(AnalysisLayer.TEMPORAL_SEGMENTATION,
        (source.output_fingerprint,),temporal_fp,1,True)
    cp=_commit_stage(runtime,ledger,envelope.owner,run_id,temporal,now=now,
        expected_revision=cp.revision)
    return VisualRuntimeIngest(source,temporal,cp,len(trace.events))
