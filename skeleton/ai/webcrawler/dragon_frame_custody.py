"""Consent-bound frame extraction contracts for Dragon recordings."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import math,json
from .dragon_consent_bound_queue import ConsentBoundAnalysisQueue

@dataclass(frozen=True)
class CapturedFrame:
    frame_id:str; owner:str; job_id:str; recording_digest:str
    consent_id:str; consent_scope_digest:str; captured_at_ms:int
    frame_digest:str; retention_until:float; source_locator:str

@dataclass(frozen=True)
class FrameBatch:
    frames:tuple[CapturedFrame,...]
    batch_fingerprint:str

def bind_extracted_frames(custody:ConsentBoundAnalysisQueue,owner:str,job_id:str,
    extracted:tuple[tuple[int,str,str],...],*,now:float,retention_until:float,
    authorized:bool,max_frames:int=100000)->FrameBatch:
    if not authorized: raise PermissionError("frame binding requires authorization")
    if not 1<=max_frames<=1000000 or len(extracted)>max_frames:
        raise ValueError("frame budget exceeded")
    if not math.isfinite(now) or now<0: raise ValueError("invalid frame binding time")
    if not math.isfinite(retention_until) or retention_until<=now:
        raise ValueError("invalid retention deadline")
    job=custody.require_active(owner,job_id,now=now,authorized=True)
    binding=custody.binding(owner,job_id,authorized=True)
    consent=custody.consent.require_active(owner,binding.consent_id,now=now,
        scope_digest=binding.scope_digest,authorized=True)
    if retention_until>consent.expires_at:
        raise PermissionError("frame retention exceeds consent lifetime")
    frames=[];last=-1;seen=set()
    for timestamp,digest,locator in extracted:
        if not isinstance(timestamp,int) or timestamp<0 or timestamp<last:
            raise ValueError("frame timestamps must be monotonic non-negative milliseconds")
        if len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("invalid frame digest")
        if not locator or len(locator)>2048: raise ValueError("invalid source locator")
        identity=sha256(("\0".join([owner,job_id,job.recording_digest,
            binding.consent_id,binding.scope_digest,str(timestamp),digest,locator])).encode()).hexdigest()
        if identity in seen: raise ValueError("duplicate frame identity")
        seen.add(identity);last=timestamp
        frames.append(CapturedFrame(identity,owner,job_id,job.recording_digest,
            binding.consent_id,binding.scope_digest,timestamp,digest,retention_until,locator))
    if not frames: raise ValueError("at least one extracted frame required")
    custody.require_active(owner,job_id,now=now,authorized=True)
    fingerprint=sha256(json.dumps([[f.frame_id,f.retention_until] for f in frames],
        separators=(",",":"),allow_nan=False).encode()).hexdigest()
    return FrameBatch(tuple(frames),fingerprint)
