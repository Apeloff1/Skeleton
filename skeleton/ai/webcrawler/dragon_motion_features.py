"""Motion-aware temporal segmentation input derived from validated visual observations."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256

from .dragon_visual_features import VisualFeatureBatch
from .dragon_temporal_segmentation import FeatureFrame

@dataclass(frozen=True)
class MotionFeatureBatch:
    frames:tuple[FeatureFrame,...]
    visual_fingerprint:str
    motion_fingerprint:str

def derive_motion_features(batch:VisualFeatureBatch,*,authorized:bool)->MotionFeatureBatch:
    if not authorized: raise PermissionError("motion derivation requires authorization")
    if not batch.frames: raise ValueError("visual feature batch is empty")
    out=[];prev=None
    for frame in batch.frames:
        lum,edge,motion,scene=frame.features
        dl=0.0 if prev is None else abs(lum-prev.features[0])
        de=0.0 if prev is None else abs(edge-prev.features[1])
        # Decoder motion remains primary; deltas expose abrupt appearance changes separately.
        features=(round(motion,9),round(scene,9),round(dl,9),round(de,9))
        out.append(FeatureFrame(frame.timestamp_ms,features,frame.source_frame_id))
        prev=frame
    fp=sha256((batch.observation_fingerprint+"\n"+"\n".join(
        f.source_frame_id+":"+":".join(map(str,f.features)) for f in out)).encode()).hexdigest()
    return MotionFeatureBatch(tuple(out),batch.observation_fingerprint,fp)
