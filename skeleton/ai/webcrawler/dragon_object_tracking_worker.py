"""Executable deterministic object-track worker for Dragon analysis.

Consumes temporal candidates plus externally extracted bounded detections.
Association is conservative and deterministic; ambiguous detections start new
tracks rather than fabricating identity continuity.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json, math

from .dragon_analysis_chains import AnalysisLayer,LayerReceipt
from .dragon_analysis_execution import LayerDispatch


@dataclass(frozen=True)
class Detection:
    frame_id: str
    timestamp_ms: int
    label: str
    confidence: float
    box: tuple[float,float,float,float]


@dataclass(frozen=True)
class ObjectTrack:
    track_id: str
    label: str
    detections: tuple[Detection,...]
    mean_confidence: float


@dataclass(frozen=True)
class ObjectTrackingOutput:
    receipt: LayerReceipt
    tracks: tuple[ObjectTrack,...]


def _center(box):
    x,y,w,h=box; return x+w/2,y+h/2


def execute_object_tracking(dispatch: LayerDispatch,
    detections: tuple[Detection,...], *, temporal_receipt: LayerReceipt,
    authorized: bool, maximum_center_distance: float=.12,
    max_detections: int=50000) -> ObjectTrackingOutput:
    if not authorized: raise PermissionError("object tracking requires authorization")
    if dispatch.layer is not AnalysisLayer.OBJECT_TRACKING:
        raise ValueError("dispatch targets another analysis layer")
    if temporal_receipt.layer is not AnalysisLayer.TEMPORAL_SEGMENTATION or not temporal_receipt.passed:
        raise ValueError("accepted temporal receipt required")
    if dispatch.input_fingerprints != (temporal_receipt.output_fingerprint,):
        raise ValueError("dispatch evidence mismatch")
    if not 0 < maximum_center_distance <= 1 or len(detections)>max_detections:
        raise ValueError("invalid tracking budget")
    ordered=sorted(detections,key=lambda d:(d.timestamp_ms,d.frame_id,d.label,d.box))
    tracks=[]
    for d in ordered:
        if not d.frame_id or d.timestamp_ms<0 or not d.label:
            raise ValueError("invalid detection identity")
        if not math.isfinite(d.confidence) or not 0<=d.confidence<=1:
            raise ValueError("invalid detection confidence")
        if len(d.box)!=4 or any(not math.isfinite(x) or not 0<=x<=1 for x in d.box):
            raise ValueError("invalid normalized box")
        x,y,w,h=d.box
        if x+w>1 or y+h>1 or w<=0 or h<=0:
            raise ValueError("invalid normalized box extent")
        candidates=[]
        cx,cy=_center(d.box)
        for i,t in enumerate(tracks):
            last=t[-1]
            if last.label!=d.label or last.timestamp_ms>=d.timestamp_ms: continue
            lx,ly=_center(last.box); dist=((cx-lx)**2+(cy-ly)**2)**.5
            if dist<=maximum_center_distance: candidates.append((dist,i))
        if candidates:
            _,idx=min(candidates,key=lambda x:(x[0],x[1])); tracks[idx].append(d)
        else: tracks.append([d])
    result=[]
    for rows in tracks:
        payload=[(x.frame_id,x.timestamp_ms,x.label,x.confidence,x.box) for x in rows]
        tid=sha256(json.dumps(payload,separators=(",",":")).encode()).hexdigest()
        result.append(ObjectTrack(tid,rows[0].label,tuple(rows),
            round(sum(x.confidence for x in rows)/len(rows),8)))
    canonical=[(t.track_id,t.label,t.mean_confidence,
        [(d.frame_id,d.timestamp_ms,d.confidence,d.box) for d in t.detections]) for t in result]
    digest=sha256(json.dumps({"input":dispatch.input_fingerprints,
        "worker":dispatch.worker,"version":dispatch.worker_version,
        "tracks":canonical},sort_keys=True,separators=(",",":")).encode()).hexdigest()
    receipt=LayerReceipt(AnalysisLayer.OBJECT_TRACKING,
        dispatch.input_fingerprints,digest,temporal_receipt.independent_sources,
        bool(detections),False)
    return ObjectTrackingOutput(receipt,tuple(result))
