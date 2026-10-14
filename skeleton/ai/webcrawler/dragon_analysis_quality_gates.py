"""Analysis chain capability registry and typed, bounded review gates.

Declares what each analysis layer must actually measure. Prevents an
unimplemented worker from passing simply by supplying a receipt.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from math import isfinite

from .dragon_analysis_chains import AnalysisLayer, LayerReceipt, validate_chain


class Measure(str, Enum):
    SOURCE_AUTHENTICITY = "source_authenticity"
    TIMESTAMP_COVERAGE = "timestamp_coverage"
    TRACK_CONTINUITY = "track_continuity"
    STATE_CONSISTENCY = "state_consistency"
    HYPOTHESIS_TESTABILITY = "hypothesis_testability"
    FALSIFICATION_COVERAGE = "falsification_coverage"
    INDEPENDENCE_COVERAGE = "independence_coverage"
    CALIBRATION_ERROR = "calibration_error"
    ONTOLOGY_CONSISTENCY = "ontology_consistency"
    ADVERSARIAL_SURVIVAL = "adversarial_survival"
    HUMAN_CONSENT = "human_consent"
    PROMOTION_INTEGRITY = "promotion_integrity"


_MEASURE = {
    AnalysisLayer.SOURCE_INTEGRITY: Measure.SOURCE_AUTHENTICITY,
    AnalysisLayer.TEMPORAL_SEGMENTATION: Measure.TIMESTAMP_COVERAGE,
    AnalysisLayer.OBJECT_TRACKING: Measure.TRACK_CONTINUITY,
    AnalysisLayer.STATE_INFERENCE: Measure.STATE_CONSISTENCY,
    AnalysisLayer.MECHANIC_HYPOTHESES: Measure.HYPOTHESIS_TESTABILITY,
    AnalysisLayer.CAUSAL_FALSIFICATION: Measure.FALSIFICATION_COVERAGE,
    AnalysisLayer.CROSS_SOURCE_CORROBORATION: Measure.INDEPENDENCE_COVERAGE,
    AnalysisLayer.UNCERTAINTY_CALIBRATION: Measure.CALIBRATION_ERROR,
    AnalysisLayer.KNOWLEDGE_NORMALIZATION: Measure.ONTOLOGY_CONSISTENCY,
    AnalysisLayer.ADVERSARIAL_REVIEW: Measure.ADVERSARIAL_SURVIVAL,
    AnalysisLayer.HUMAN_APPROVAL: Measure.HUMAN_CONSENT,
    AnalysisLayer.MEMORY_PROMOTION: Measure.PROMOTION_INTEGRITY,
}


@dataclass(frozen=True)
class Measurement:
    layer: AnalysisLayer
    measure: Measure
    value: float
    sample_count: int
    evidence_digest: str


@dataclass(frozen=True)
class GatePolicy:
    minimum_sample_count: int = 3
    minimum_quality: float = 0.75
    maximum_calibration_error: float = 0.10


@dataclass(frozen=True)
class AnalysisGateReport:
    accepted: bool
    failures: tuple[str, ...]
    measurement_fingerprint: str


def gate_analysis(
    receipts: tuple[LayerReceipt, ...],
    measurements: tuple[Measurement, ...], *,
    authorized: bool,
    policy: GatePolicy = GatePolicy(),
) -> AnalysisGateReport:
    if not authorized:
        raise PermissionError("analysis gate requires authorization")
    if not 1 <= policy.minimum_sample_count <= 100000:
        raise ValueError("invalid sample threshold")
    if not 0 <= policy.minimum_quality <= 1 or not 0 <= policy.maximum_calibration_error <= 1:
        raise ValueError("invalid quality thresholds")
    verdict = validate_chain(receipts, authorized=True)
    by_layer = {}
    for item in measurements:
        if item.layer in by_layer:
            raise ValueError("duplicate layer measurement")
        if _MEASURE.get(item.layer) != item.measure:
            raise ValueError("measurement does not match layer")
        if not isfinite(item.value) or not 0 <= item.value <= 1:
            raise ValueError("invalid measurement")
        if not isinstance(item.sample_count, int) or item.sample_count < 0:
            raise ValueError("invalid sample count")
        if not isinstance(item.evidence_digest, str) or len(item.evidence_digest) != 64 or any(
            ch not in "0123456789abcdef" for ch in item.evidence_digest
        ):
            raise ValueError("invalid measurement evidence")
        by_layer[item.layer] = item
    failures = []
    if not verdict.complete:
        failures.append("Analysis chain incomplete or rejected")
    for layer, expected in _MEASURE.items():
        item = by_layer.get(layer)
        if item is None:
            failures.append(f"{layer.value}: missing measurement")
            continue
        if item.sample_count < policy.minimum_sample_count:
            failures.append(f"{layer.value}: insufficient samples")
        if layer is AnalysisLayer.UNCERTAINTY_CALIBRATION:
            if item.value > policy.maximum_calibration_error:
                failures.append(f"{layer.value}: calibration error too high")
        elif item.value < policy.minimum_quality:
            failures.append(f"{layer.value}: quality below threshold")
        receipt = next((r for r in receipts if r.layer == layer), None)
        if receipt is None or receipt.output_fingerprint != item.evidence_digest:
            failures.append(f"{layer.value}: measurement evidence not bound to receipt")
    fingerprint = sha256(json.dumps(sorted(
        (x.layer.value, x.measure.value, x.value, x.sample_count, x.evidence_digest)
        for x in measurements
    ), separators=(",", ":")).encode()).hexdigest()
    return AnalysisGateReport(not failures, tuple(failures), fingerprint)
