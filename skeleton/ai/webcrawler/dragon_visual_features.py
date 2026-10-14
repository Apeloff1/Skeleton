"""Validated visual observations from a local gameplay frame decoder."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite

from .dragon_frame_custody import FrameBatch
from .dragon_temporal_segmentation import FeatureFrame
from .dragon_consent_bound_queue import ConsentBoundAnalysisQueue

@dataclass(frozen=True)
class VisualObservation:
    frame_id:str
    frame_digest:str
    luminance_mean:float
    edge_density:float
    motion_energy:float
    scene_change:float

@dataclass(frozen=True)
class VisualFeatureBatch:
    frames:tuple[FeatureFrame,...]
    observation_fingerprint:str
    source_batch_fingerprint:str

def bind_visual_observations(custody:ConsentBoundAnalysisQueue,owner:str,job_id:str,
    source:FrameBatch,observations:tuple[VisualObservation,...],*,now:float,
    authorized:bool)->VisualFeatureBatch:
    if not authorized: raise PermissionError("visual feature binding requires authorization")
    custody.require_active(owner,job_id,now=now,authorized=True)
    if len(observations)!=len(source.frames): raise ValueError("visual observation coverage mismatch")
    out=[]; canonical=[]
    for frame,obs in zip(source.frames,observations):
        if frame.owner!=owner or frame.job_id!=job_id: raise ValueError("frame owner/job substitution")
        if now>=frame.retention_until: raise PermissionError("frame retention expired")
        if obs.frame_id!=frame.frame_id or obs.frame_digest!=frame.frame_digest:
            raise ValueError("decoder observation does not bind source frame")
        values=(obs.luminance_mean,obs.edge_density,obs.motion_energy,obs.scene_change)
        if any(not isinstance(x,(int,float)) or not isfinite(x) or x<0 or x>1 for x in values):
            raise ValueError("decoder features must be finite normalized values")
        rounded=tuple(round(float(x),9) for x in values)
        out.append(FeatureFrame(frame.captured_at_ms,rounded,frame.frame_id))
        canonical.append(frame.frame_id+":"+":".join(map(str,rounded)))
    custody.require_active(owner,job_id,now=now,authorized=True)
    fp=sha256((source.batch_fingerprint+"\n"+"\n".join(canonical)).encode()).hexdigest()
    return VisualFeatureBatch(tuple(out),fp,source.batch_fingerprint)
