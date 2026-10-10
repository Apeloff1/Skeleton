"""Executable falsifiable-hypothesis worker for observed Dragon states."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json

from .dragon_analysis_chains import AnalysisLayer,LayerReceipt
from .dragon_analysis_execution import LayerDispatch
from .dragon_hypothesis_registry import MechanicHypothesis
from .dragon_state_inference_worker import TrackState


@dataclass(frozen=True)
class HypothesisCandidate:
    hypothesis: MechanicHypothesis
    intervention: str
    measured_outcome: str
    alternative_explanation: str


@dataclass(frozen=True)
class HypothesisWorkerOutput:
    receipt: LayerReceipt
    candidates: tuple[HypothesisCandidate,...]


def execute_hypothesis_generation(dispatch: LayerDispatch,
    states: tuple[TrackState,...], *, state_receipt: LayerReceipt,
    authorized: bool, max_hypotheses: int=1000) -> HypothesisWorkerOutput:
    if not authorized: raise PermissionError("hypothesis generation requires authorization")
    if dispatch.layer is not AnalysisLayer.MECHANIC_HYPOTHESES:
        raise ValueError("dispatch targets another analysis layer")
    if state_receipt.layer is not AnalysisLayer.STATE_INFERENCE or not state_receipt.passed:
        raise ValueError("accepted state inference receipt required")
    if dispatch.input_fingerprints != (state_receipt.output_fingerprint,):
        raise ValueError("dispatch evidence mismatch")
    if not 1<=max_hypotheses<=10000: raise ValueError("invalid hypothesis budget")
    candidates=[]
    for state in sorted(states,key=lambda x:x.track_id):
        if len(candidates)>=max_hypotheses: break
        if state.state!="moving": continue
        # Candidate deliberately says association, not causation. A later
        # intervention protocol must test whether an input controls this track.
        mechanic=f"candidate_control_of_{state.label}"
        statement=f"An intervention may alter motion of observed {state.label} track."
        predicted=f"Pre-registered intervention is followed by reproducible displacement change in track {state.track_id}."
        falsifying=f"Matched intervention/control trials show no reproducible displacement difference for track {state.track_id}."
        hid=sha256(json.dumps([state_receipt.output_fingerprint,state.track_id,
            mechanic],separators=(",",":")).encode()).hexdigest()
        h=MechanicHypothesis(hid,mechanic,statement,predicted,falsifying,
            state_receipt.output_fingerprint)
        candidates.append(HypothesisCandidate(h,
            "apply a pre-registered candidate input under matched conditions",
            "change in normalized track displacement over a fixed time window",
            "camera motion, animation, scripted motion, detection drift, or correlated input"))
    canonical=[(c.hypothesis.hypothesis_id,c.hypothesis.mechanic,
        c.hypothesis.statement,c.hypothesis.predicted_observation,
        c.hypothesis.falsifying_observation,c.intervention,
        c.measured_outcome,c.alternative_explanation) for c in candidates]
    digest=sha256(json.dumps({"input":dispatch.input_fingerprints,
        "worker":dispatch.worker,"version":dispatch.worker_version,
        "candidates":canonical},sort_keys=True,separators=(",",":")).encode()).hexdigest()
    receipt=LayerReceipt(AnalysisLayer.MECHANIC_HYPOTHESES,
        dispatch.input_fingerprints,digest,state_receipt.independent_sources,
        bool(candidates),False)
    return HypothesisWorkerOutput(receipt,tuple(candidates))
