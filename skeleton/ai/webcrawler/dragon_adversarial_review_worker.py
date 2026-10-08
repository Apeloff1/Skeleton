"""Executable adversarial review for normalized Dragon knowledge."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json,math

from .dragon_analysis_chains import AnalysisLayer,LayerReceipt
from .dragon_analysis_execution import LayerDispatch
from .dragon_knowledge_normalization_worker import NormalizedKnowledge
from .dragon_knowledge_manifest import canonical_knowledge_id


@dataclass(frozen=True)
class AdversarialFinding:
    knowledge_id:str
    attack:str
    severity:str
    passed:bool
    reason:str


@dataclass(frozen=True)
class AdversarialReviewOutput:
    receipt:LayerReceipt
    findings:tuple[AdversarialFinding,...]
    surviving_knowledge_ids:tuple[str,...]


def _hex64(value:str)->bool:
    return isinstance(value,str) and len(value)==64 and all(c in "0123456789abcdef" for c in value)


def execute_adversarial_review(dispatch:LayerDispatch,
    records:tuple[NormalizedKnowledge,...],*,normalization_receipt:LayerReceipt,
    authorized:bool)->AdversarialReviewOutput:
    if not authorized: raise PermissionError("adversarial review requires authorization")
    if dispatch.layer is not AnalysisLayer.ADVERSARIAL_REVIEW:
        raise ValueError("dispatch targets another analysis layer")
    if normalization_receipt.layer is not AnalysisLayer.KNOWLEDGE_NORMALIZATION or not normalization_receipt.passed:
        raise ValueError("accepted normalization receipt required")
    if dispatch.input_fingerprints!=(normalization_receipt.output_fingerprint,):
        raise ValueError("dispatch evidence mismatch")
    findings=[];survivors=[]
    seen_knowledge=set();seen_hypotheses=set()
    for r in sorted(records,key=lambda x:x.knowledge_id):
        checks=[
            ("identity_integrity","critical",_hex64(r.knowledge_id) and r.knowledge_id==canonical_knowledge_id(r),"knowledge identity/content binding is not canonical"),
            ("evidence_integrity","critical",_hex64(r.evidence_fingerprint),"upstream evidence fingerprint missing or malformed"),
            ("calibration_integrity","critical",_hex64(r.calibration_artifact_fingerprint),"calibration artifact identity missing or malformed"),
            ("probability_semantics","critical",r.probability_semantics=="empirically_calibrated_probability","probability is not empirically calibrated"),
            ("probability_bounds","critical",isinstance(r.probability,(int,float)) and math.isfinite(r.probability) and 0<=r.probability<=1,"probability outside valid bounds"),
            ("contradiction_suppression","high",r.contradiction_state!="unresolved","unresolved contradiction cannot advance"),
            ("verdict_scope","high",r.verdict in {"supported","refuted"},"inconclusive verdict cannot advance as knowledge"),
            ("identity_replay","critical",r.knowledge_id not in seen_knowledge,"duplicate knowledge identity replay"),
            ("hypothesis_duplication","high",r.hypothesis_id not in seen_hypotheses,"duplicate hypothesis represented multiple times"),
        ]
        passed_all=True
        for attack,severity,passed,reason in checks:
            findings.append(AdversarialFinding(r.knowledge_id,attack,severity,bool(passed),
                "survived" if passed else reason))
            passed_all &= bool(passed)
        seen_knowledge.add(r.knowledge_id);seen_hypotheses.add(r.hypothesis_id)
        if passed_all: survivors.append(r.knowledge_id)
    canonical=[vars(x) for x in findings]
    digest=sha256(json.dumps({"input":dispatch.input_fingerprints,
        "worker":dispatch.worker,"version":dispatch.worker_version,
        "findings":canonical,"survivors":survivors},
        sort_keys=True,separators=(",",":")).encode()).hexdigest()
    receipt=LayerReceipt(AnalysisLayer.ADVERSARIAL_REVIEW,
        dispatch.input_fingerprints,digest,normalization_receipt.independent_sources,
        bool(records) and len(survivors)==len(records),False)
    return AdversarialReviewOutput(receipt,tuple(findings),tuple(survivors))
