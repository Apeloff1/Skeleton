"""Consent-bound execution wrapper for temporal gameplay analysis."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
import json

from .dragon_analysis_chains import LayerReceipt
from .dragon_analysis_execution import LayerDispatch
from .dragon_consent_bound_queue import ConsentBoundAnalysisQueue
from .dragon_temporal_segmentation import FeatureFrame, SegmentationConfig
from .dragon_temporal_worker import TemporalWorkerOutput, execute_temporal_dispatch


@dataclass(frozen=True)
class CustodiedTemporalOutput:
    output: TemporalWorkerOutput
    job_id: str
    recording_digest: str
    consent_id: str
    consent_scope_digest: str
    custody_fingerprint: str


def execute_consent_bound_temporal(
    custody: ConsentBoundAnalysisQueue, owner: str, job_id: str,
    dispatch: LayerDispatch, frames: tuple[FeatureFrame, ...], *,
    now: float, source_integrity_receipt: LayerReceipt,
    authorized: bool, config: SegmentationConfig = SegmentationConfig(),
) -> CustodiedTemporalOutput:
    if not authorized:
        raise PermissionError("custodied temporal execution requires authorization")
    job=custody.require_active(owner,job_id,now=now,authorized=True)
    binding=custody.binding(owner,job_id,authorized=True)
    output=execute_temporal_dispatch(
        dispatch,frames,authorized=True,
        source_integrity_receipt=source_integrity_receipt,config=config)
    # Re-check after work. A future long-running worker can checkpoint this
    # same invariant between batches; this already prevents returning results
    # when consent expired/revoked during the operation.
    custody.require_active(owner,job_id,now=now,authorized=True)
    payload={
        "owner":owner,"job_id":job_id,
        "recording_digest":job.recording_digest,
        "consent_id":binding.consent_id,
        "scope_digest":binding.scope_digest,
        "temporal_output":output.receipt.output_fingerprint,
        "source_integrity":source_integrity_receipt.output_fingerprint,
    }
    fingerprint=sha256(json.dumps(
        payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return CustodiedTemporalOutput(
        output,job_id,job.recording_digest,binding.consent_id,
        binding.scope_digest,fingerprint)
