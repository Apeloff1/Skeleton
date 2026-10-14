"""Executable conservative state inference from object tracks."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json

from .dragon_analysis_chains import AnalysisLayer,LayerReceipt
from .dragon_analysis_execution import LayerDispatch
from .dragon_object_tracking_worker import ObjectTrack


@dataclass(frozen=True)
class TrackState:
    track_id: str
    label: str
    first_ms: int
    last_ms: int
    observation_count: int
    displacement: float
    confidence: float
    state: str


@dataclass(frozen=True)
class StateInferenceOutput:
    receipt: LayerReceipt
    states: tuple[TrackState,...]


def execute_state_inference(dispatch: LayerDispatch,
    tracks: tuple[ObjectTrack,...], *, tracking_receipt: LayerReceipt,
    authorized: bool, movement_threshold: float=.03,
    max_tracks: int=10000) -> StateInferenceOutput:
    if not authorized: raise PermissionError("state inference requires authorization")
    if dispatch.layer is not AnalysisLayer.STATE_INFERENCE:
        raise ValueError("dispatch targets another analysis layer")
    if tracking_receipt.layer is not AnalysisLayer.OBJECT_TRACKING or not tracking_receipt.passed:
        raise ValueError("accepted object tracking receipt required")
    if dispatch.input_fingerprints != (tracking_receipt.output_fingerprint,):
        raise ValueError("dispatch evidence mismatch")
    if not 0<=movement_threshold<=1 or len(tracks)>max_tracks:
        raise ValueError("invalid inference budget")
    states=[]
    for track in sorted(tracks,key=lambda x:x.track_id):
        if not track.detections: raise ValueError("empty object track")
        first,last=track.detections[0],track.detections[-1]
        fc=(first.box[0]+first.box[2]/2,first.box[1]+first.box[3]/2)
        lc=(last.box[0]+last.box[2]/2,last.box[1]+last.box[3]/2)
        displacement=((lc[0]-fc[0])**2+(lc[1]-fc[1])**2)**.5
        # Only infer observable kinematic state. No gameplay semantics.
        state="moving" if len(track.detections)>1 and displacement>=movement_threshold else "stationary_or_unresolved"
        states.append(TrackState(track.track_id,track.label,first.timestamp_ms,
            last.timestamp_ms,len(track.detections),round(displacement,8),
            track.mean_confidence,state))
    payload=[vars(x) for x in states]
    digest=sha256(json.dumps({"input":dispatch.input_fingerprints,
        "worker":dispatch.worker,"version":dispatch.worker_version,
        "states":payload},sort_keys=True,separators=(",",":")).encode()).hexdigest()
    receipt=LayerReceipt(AnalysisLayer.STATE_INFERENCE,
        dispatch.input_fingerprints,digest,tracking_receipt.independent_sources,
        bool(states),False)
    return StateInferenceOutput(receipt,tuple(states))
