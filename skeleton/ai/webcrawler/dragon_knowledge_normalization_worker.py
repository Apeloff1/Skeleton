"""Executable versioned knowledge-normalization layer for Dragon findings."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json

from .dragon_analysis_chains import AnalysisLayer,LayerReceipt
from .dragon_analysis_execution import LayerDispatch
from .dragon_uncertainty_calibration_worker import CalibratedClaim


@dataclass(frozen=True)
class NormalizedKnowledge:
    knowledge_id:str
    hypothesis_id:str
    ontology_version:str
    verdict:str
    probability:float
    probability_semantics:str
    calibration_artifact_fingerprint:str
    evidence_fingerprint:str
    contradiction_state:str


@dataclass(frozen=True)
class KnowledgeNormalizationOutput:
    receipt:LayerReceipt
    records:tuple[NormalizedKnowledge,...]


def execute_knowledge_normalization(dispatch:LayerDispatch,
    claims:tuple[CalibratedClaim,...],*,calibration_receipt:LayerReceipt,
    authorized:bool,ontology_version:str="dragon.game-knowledge.v1"
    )->KnowledgeNormalizationOutput:
    if not authorized: raise PermissionError("knowledge normalization requires authorization")
    if dispatch.layer is not AnalysisLayer.KNOWLEDGE_NORMALIZATION:
        raise ValueError("dispatch targets another analysis layer")
    if calibration_receipt.layer is not AnalysisLayer.UNCERTAINTY_CALIBRATION or not calibration_receipt.passed:
        raise ValueError("accepted calibration receipt required")
    if dispatch.input_fingerprints!=(calibration_receipt.output_fingerprint,):
        raise ValueError("dispatch evidence mismatch")
    if not isinstance(ontology_version,str) or not 1<=len(ontology_version)<=128:
        raise ValueError("invalid ontology version")
    records=[]
    seen=set()
    for c in sorted(claims,key=lambda x:x.hypothesis_id):
        if c.hypothesis_id in seen: raise ValueError("duplicate calibrated claim")
        seen.add(c.hypothesis_id)
        if c.probability_semantics!="empirically_calibrated_probability":
            raise ValueError("normalization refuses non-calibrated probability semantics")
        contradiction=("resolved_support" if c.corroboration_verdict=="supported"
            else "resolved_refutation" if c.corroboration_verdict=="refuted"
            else "unresolved")
        identity=[c.hypothesis_id,ontology_version,c.corroboration_verdict,
            c.calibrated_probability,c.probability_semantics,
            c.calibration_artifact_fingerprint,calibration_receipt.output_fingerprint]
        kid=sha256(json.dumps(identity,separators=(",",":")).encode()).hexdigest()
        records.append(NormalizedKnowledge(kid,c.hypothesis_id,ontology_version,
            c.corroboration_verdict,c.calibrated_probability,
            c.probability_semantics,c.calibration_artifact_fingerprint,
            calibration_receipt.output_fingerprint,contradiction))
    canonical=[vars(x) for x in records]
    digest=sha256(json.dumps({"input":dispatch.input_fingerprints,
        "worker":dispatch.worker,"version":dispatch.worker_version,
        "ontology":ontology_version,"records":canonical},
        sort_keys=True,separators=(",",":")).encode()).hexdigest()
    receipt=LayerReceipt(AnalysisLayer.KNOWLEDGE_NORMALIZATION,
        dispatch.input_fingerprints,digest,calibration_receipt.independent_sources,
        bool(records),False)
    return KnowledgeNormalizationOutput(receipt,tuple(records))
