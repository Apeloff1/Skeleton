"""Deterministic feature extraction from custodied gameplay frame metadata.

This worker intentionally extracts metadata-domain temporal signals only.
Pixel-derived features belong to the local capture decoder; they can be
appended later without weakening provenance or consent custody.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import math

from .dragon_frame_custody import FrameBatch
from .dragon_temporal_segmentation import FeatureFrame
from .dragon_consent_bound_queue import ConsentBoundAnalysisQueue

@dataclass(frozen=True)
class FeatureBatch:
    frames:tuple[FeatureFrame,...]
    frame_batch_fingerprint:str
    feature_fingerprint:str

def extract_custodied_features(custody:ConsentBoundAnalysisQueue,owner:str,job_id:str,
    batch:FrameBatch,*,now:float,authorized:bool)->FeatureBatch:
    if not authorized: raise PermissionError("feature extraction requires authorization")
    job=custody.require_active(owner,job_id,now=now,authorized=True)
    binding=custody.binding(owner,job_id,authorized=True)
    if not batch.frames: raise ValueError("empty frame batch")
    out=[]; previous=None
    for f in batch.frames:
        if f.owner!=owner or f.job_id!=job_id or f.recording_digest!=job.recording_digest:
            raise ValueError("frame custody substitution")
        if f.consent_id!=binding.consent_id or f.consent_scope_digest!=binding.scope_digest:
            raise ValueError("frame consent substitution")
        if now>=f.retention_until: raise PermissionError("frame retention expired")
        gap=0.0 if previous is None else min((f.captured_at_ms-previous)/1000.0,1.0)
        digest_signal=int(f.frame_digest[:8],16)/0xffffffff
        locator_signal=int(sha256(f.source_locator.encode()).hexdigest()[:8],16)/0xffffffff
        out.append(FeatureFrame(f.captured_at_ms,
            (round(digest_signal,9),round(locator_signal,9),round(gap,9)),f.frame_id))
        previous=f.captured_at_ms
    custody.require_active(owner,job_id,now=now,authorized=True)
    fp=sha256((batch.batch_fingerprint+"\n"+"\n".join(
        x.source_frame_id+":"+",".join(map(str,x.features)) for x in out)).encode()).hexdigest()
    return FeatureBatch(tuple(out),batch.batch_fingerprint,fp)
