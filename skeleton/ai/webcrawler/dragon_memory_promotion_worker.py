"""Final promotion gate for adversarially reviewed, human-approved Dragon knowledge."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json

from .dragon_analysis_chains import AnalysisLayer,LayerReceipt
from .dragon_analysis_execution import LayerDispatch
from .dragon_human_review import HumanReviewDecision
from .dragon_knowledge_normalization_worker import NormalizedKnowledge


@dataclass(frozen=True)
class PromotedKnowledge:
    knowledge_id:str
    hypothesis_id:str
    probability:float
    ontology_version:str
    human_review_id:str
    promotion_fingerprint:str


@dataclass(frozen=True)
class MemoryPromotionOutput:
    receipt:LayerReceipt
    promoted:tuple[PromotedKnowledge,...]


def execute_memory_promotion(dispatch:LayerDispatch,
    records:tuple[NormalizedKnowledge,...],*,human_receipt:LayerReceipt,
    human_decision:HumanReviewDecision,surviving_knowledge_ids:tuple[str,...],
    authorized:bool,minimum_probability:float=.9)->MemoryPromotionOutput:
    if not authorized: raise PermissionError("memory promotion requires authorization")
    if dispatch.layer is not AnalysisLayer.MEMORY_PROMOTION:
        raise ValueError("dispatch targets another analysis layer")
    if human_receipt.layer is not AnalysisLayer.HUMAN_APPROVAL or not human_receipt.passed or not human_receipt.human_approved:
        raise PermissionError("explicit passing human approval required")
    if dispatch.input_fingerprints!=(human_receipt.output_fingerprint,):
        raise ValueError("dispatch evidence mismatch")
    if human_decision.review_id!=human_receipt.output_fingerprint or not human_decision.approved:
        raise ValueError("human decision does not bind approval receipt")
    if not .5<minimum_probability<1: raise ValueError("invalid promotion threshold")
    survivors=tuple(sorted(surviving_knowledge_ids))
    digest=sha256(json.dumps(survivors,separators=(",",":")).encode()).hexdigest()
    if digest!=human_decision.survivor_digest:
        raise PermissionError("approved survivor set changed after human review")
    by_id={r.knowledge_id:r for r in records}
    if len(by_id)!=len(records): raise ValueError("duplicate normalized knowledge identity")
    if set(survivors)-set(by_id): raise ValueError("approved survivor missing normalized record")
    promoted=[]
    for kid in survivors:
        r=by_id[kid]
        if r.probability_semantics!="empirically_calibrated_probability":
            raise PermissionError("promotion requires calibrated probability")
        if r.contradiction_state=="unresolved":
            raise PermissionError("unresolved contradiction cannot be promoted")
        if r.verdict!="supported" or r.probability<minimum_probability:
            continue
        fp=sha256(json.dumps([r.knowledge_id,r.evidence_fingerprint,
            r.calibration_artifact_fingerprint,human_decision.review_id,
            r.ontology_version],separators=(",",":")).encode()).hexdigest()
        promoted.append(PromotedKnowledge(r.knowledge_id,r.hypothesis_id,
            r.probability,r.ontology_version,human_decision.review_id,fp))
    output_digest=sha256(json.dumps([vars(x) for x in promoted],
        sort_keys=True,separators=(",",":")).encode()).hexdigest()
    receipt=LayerReceipt(AnalysisLayer.MEMORY_PROMOTION,
        dispatch.input_fingerprints,output_digest,human_receipt.independent_sources,
        bool(promoted),False)
    return MemoryPromotionOutput(receipt,tuple(promoted))
