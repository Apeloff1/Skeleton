"""Executable, deterministic temporal worker with verifiable evidence custody.

The worker consumes explicit, consented feature frames and emits a canonical
output digest. It cannot certify its own source-integrity prerequisite or
promote semantic mechanic claims.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from .dragon_analysis_chains import AnalysisLayer, LayerReceipt
from .dragon_analysis_execution import LayerDispatch
from .dragon_temporal_segmentation import (
    FeatureFrame, SegmentationConfig, TemporalEvent, segment_feature_trace,
)


@dataclass(frozen=True)
class TemporalWorkerOutput:
    receipt: LayerReceipt
    events: tuple[TemporalEvent, ...]
    event_count: int
    frame_count: int


def _fingerprint(payload: object) -> str:
    return sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")).hexdigest()


def execute_temporal_dispatch(
    dispatch: LayerDispatch,
    frames: tuple[FeatureFrame, ...], *,
    authorized: bool,
    source_integrity_receipt: LayerReceipt,
    config: SegmentationConfig = SegmentationConfig(),
) -> TemporalWorkerOutput:
    if not authorized:
        raise PermissionError("temporal worker requires authorization")
    if dispatch.layer is not AnalysisLayer.TEMPORAL_SEGMENTATION:
        raise ValueError("dispatch targets another analysis layer")
    if source_integrity_receipt.layer is not AnalysisLayer.SOURCE_INTEGRITY:
        raise ValueError("source integrity receipt required")
    if not source_integrity_receipt.passed:
        raise ValueError("source integrity prerequisite failed")
    if source_integrity_receipt.input_fingerprints:
        raise ValueError("source integrity root must have no layer dependencies")
    if dispatch.input_fingerprints != (source_integrity_receipt.output_fingerprint,):
        raise ValueError("dispatch evidence does not match source integrity")
    if len(source_integrity_receipt.output_fingerprint) != 64 or any(
        x not in "0123456789abcdef" for x in source_integrity_receipt.output_fingerprint
    ):
        raise ValueError("invalid source integrity digest")
    if not isinstance(dispatch.worker, str) or not dispatch.worker:
        raise ValueError("worker identity missing")
    if not isinstance(dispatch.worker_version, str) or not dispatch.worker_version:
        raise ValueError("worker version missing")
    events = segment_feature_trace(frames, authorized=True, config=config)
    canonical_events = [
        {
            "start_ms": e.start_ms,
            "peak_ms": e.peak_ms,
            "end_ms": e.end_ms,
            "peak_change": e.peak_change,
            "baseline_change": e.baseline_change,
            "feature_indices": list(e.feature_indices),
            "source_frame_ids": list(e.source_frame_ids),
            "interpretation": e.interpretation,
        }
        for e in events
    ]
    digest = _fingerprint({
        "worker": dispatch.worker,
        "version": dispatch.worker_version,
        "source_integrity": source_integrity_receipt.output_fingerprint,
        "config": vars(config),
        "frames": [
            (f.timestamp_ms, f.source_frame_id, list(f.features)) for f in frames
        ],
        "events": canonical_events,
    })
    receipt = LayerReceipt(
        layer=AnalysisLayer.TEMPORAL_SEGMENTATION,
        input_fingerprints=dispatch.input_fingerprints,
        output_fingerprint=digest,
        independent_sources=source_integrity_receipt.independent_sources,
        passed=bool(frames),
        human_approved=False,
    )
    return TemporalWorkerOutput(receipt, events, len(events), len(frames))
