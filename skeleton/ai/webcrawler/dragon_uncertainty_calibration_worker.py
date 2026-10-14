"""Executable held-out uncertainty-calibration layer."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json,math

from .dragon_analysis_chains import AnalysisLayer,LayerReceipt
from .dragon_analysis_execution import LayerDispatch
from .dragon_cross_source_worker import CorroboratedClaim
from .dragon_empirical_calibration import CalibrationArtifact,apply_calibrator


@dataclass(frozen=True)
class CalibratedClaim:
    hypothesis_id:str
    corroboration_verdict:str
    raw_evidence_score:float
    calibrated_probability:float
    probability_semantics:str
    calibration_artifact_fingerprint:str


@dataclass(frozen=True)
class UncertaintyCalibrationOutput:
    receipt:LayerReceipt
    claims:tuple[CalibratedClaim,...]


def execute_uncertainty_calibration(dispatch:LayerDispatch,
    claims:tuple[CorroboratedClaim,...],raw_scores:dict[str,float], *,
    corroboration_receipt:LayerReceipt,artifact:CalibrationArtifact,
    authorized:bool)->UncertaintyCalibrationOutput:
    if not authorized: raise PermissionError("uncertainty calibration requires authorization")
    if dispatch.layer is not AnalysisLayer.UNCERTAINTY_CALIBRATION:
        raise ValueError("dispatch targets another analysis layer")
    if corroboration_receipt.layer is not AnalysisLayer.CROSS_SOURCE_CORROBORATION or not corroboration_receipt.passed:
        raise ValueError("accepted corroboration receipt required")
    if dispatch.input_fingerprints!=(corroboration_receipt.output_fingerprint,):
        raise ValueError("dispatch evidence mismatch")
    if not artifact.eligible:
        raise ValueError("held-out calibration artifact is not eligible")
    if len(artifact.artifact_fingerprint)!=64:
        raise ValueError("invalid calibration artifact fingerprint")
    output=[]
    expected={x.hypothesis_id for x in claims}
    if set(raw_scores)!=expected:
        raise ValueError("raw score coverage must exactly match corroborated claims")
    for claim in sorted(claims,key=lambda x:x.hypothesis_id):
        score=raw_scores[claim.hypothesis_id]
        if not isinstance(score,(int,float)) or not math.isfinite(score) or not 0<=score<=1:
            raise ValueError("invalid raw evidence score")
        calibrated=apply_calibrator(float(score),artifact,authorized=True)
        output.append(CalibratedClaim(
            claim.hypothesis_id,claim.verdict,float(score),
            calibrated.calibrated_probability,
            "empirically_calibrated_probability",
            calibrated.artifact_fingerprint))
    canonical=[vars(x) for x in output]
    digest=sha256(json.dumps({"input":dispatch.input_fingerprints,
        "worker":dispatch.worker,"version":dispatch.worker_version,
        "artifact":artifact.artifact_fingerprint,
        "evaluation":artifact.evaluation.fingerprint,
        "claims":canonical},sort_keys=True,separators=(",",":")).encode()).hexdigest()
    receipt=LayerReceipt(AnalysisLayer.UNCERTAINTY_CALIBRATION,
        dispatch.input_fingerprints,digest,corroboration_receipt.independent_sources,
        bool(output),False)
    return UncertaintyCalibrationOutput(receipt,tuple(output))
