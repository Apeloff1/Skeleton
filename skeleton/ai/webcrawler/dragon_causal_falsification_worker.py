"""Executable causal-falsification worker for preregistered mechanic trials."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json

from .dragon_analysis_chains import AnalysisLayer,LayerReceipt
from .dragon_analysis_execution import LayerDispatch
from .dragon_hypothesis_worker import HypothesisCandidate
from .dragon_mechanic_causal_analysis import MechanicEffect,analyze_mechanic_trials
from .dragon_trial_ledger import DragonTrialLedger


@dataclass(frozen=True)
class FalsificationOutcome:
    hypothesis_id:str
    verdict:str
    effect:MechanicEffect
    trial_evidence_digest:str


@dataclass(frozen=True)
class CausalFalsificationOutput:
    receipt:LayerReceipt
    outcomes:tuple[FalsificationOutcome,...]


def execute_causal_falsification(dispatch:LayerDispatch,
    candidates:tuple[HypothesisCandidate,...],*,hypothesis_receipt:LayerReceipt,
    trial_ledger:DragonTrialLedger,owner:str,
    protocol_by_hypothesis:dict[str,str],authorized:bool,
    minimum_per_arm:int=10)->CausalFalsificationOutput:
    if not authorized: raise PermissionError("causal falsification requires authorization")
    if dispatch.layer is not AnalysisLayer.CAUSAL_FALSIFICATION:
        raise ValueError("dispatch targets another analysis layer")
    if hypothesis_receipt.layer is not AnalysisLayer.MECHANIC_HYPOTHESES or not hypothesis_receipt.passed:
        raise ValueError("accepted hypothesis receipt required")
    if dispatch.input_fingerprints!=(hypothesis_receipt.output_fingerprint,):
        raise ValueError("dispatch evidence mismatch")
    outcomes=[]
    for candidate in sorted(candidates,key=lambda x:x.hypothesis.hypothesis_id):
        hid=candidate.hypothesis.hypothesis_id
        protocol_id=protocol_by_hypothesis.get(hid)
        if not protocol_id: continue
        trials,protocol=trial_ledger.materialize(owner,protocol_id,authorized=True)
        if len(trials)<2: continue
        effect=analyze_mechanic_trials(trials,authorized=True,
            minimum_per_arm=minimum_per_arm,protocol=protocol)
        low,high=effect.difference_interval
        # Conservative evidence classification: interval wholly positive
        # supports the candidate; interval containing zero is inconclusive;
        # wholly non-positive falsifies the predicted positive effect.
        if effect.causal_claim_permitted and low>0: verdict="supported"
        elif effect.causal_claim_permitted and high<=0: verdict="refuted"
        else: verdict="inconclusive"
        digest=sha256(json.dumps([
            protocol.protocol_id,protocol.assignment_digest,
            [(t.trial_id,t.intervention,t.outcome_success,t.context_group,t.source_id)
             for t in trials],effect.observed_difference,effect.difference_interval,
            verdict],separators=(",",":")).encode()).hexdigest()
        outcomes.append(FalsificationOutcome(hid,verdict,effect,digest))
    canonical=[(x.hypothesis_id,x.verdict,x.trial_evidence_digest,
        x.effect.observed_difference,x.effect.difference_interval,
        x.effect.causal_claim_permitted) for x in outcomes]
    digest=sha256(json.dumps({"input":dispatch.input_fingerprints,
        "worker":dispatch.worker,"version":dispatch.worker_version,
        "outcomes":canonical},sort_keys=True,separators=(",",":")).encode()).hexdigest()
    receipt=LayerReceipt(AnalysisLayer.CAUSAL_FALSIFICATION,
        dispatch.input_fingerprints,digest,hypothesis_receipt.independent_sources,
        bool(outcomes),False)
    return CausalFalsificationOutput(receipt,tuple(outcomes))
