"""Tests for analysis quality gates and falsifiable hypothesis custody."""
import sqlite3
import pytest

from skeleton.ai.webcrawler.dragon_analysis_chains import (
    DEFAULT_CHAIN, LayerReceipt, AnalysisLayer,
)
from skeleton.ai.webcrawler.dragon_analysis_quality_gates import (
    Measure, Measurement, gate_analysis,
)
from skeleton.ai.webcrawler.dragon_hypothesis_registry import (
    DragonHypothesisRegistry, MechanicHypothesis, HypothesisResult,
    HypothesisState,
)


def chain():
    receipts, measurements, outputs = [], [], {}
    measures = list(Measure)
    for index, spec in enumerate(DEFAULT_CHAIN):
        digest = f"{index+1:064x}"
        receipts.append(LayerReceipt(
            spec.layer, tuple(outputs[dep] for dep in spec.dependencies),
            digest, 2, True, spec.requires_human,
        ))
        measurements.append(Measurement(
            spec.layer, measures[index],
            0.02 if spec.layer is AnalysisLayer.UNCERTAINTY_CALIBRATION else .95,
            40, digest,
        ))
        outputs[spec.layer] = digest
    return tuple(receipts), tuple(measurements)


def test_valid_measurements_pass_gate():
    receipts, measurements = chain()
    assert gate_analysis(receipts, measurements, authorized=True).accepted


def test_missing_measurement_fails():
    receipts, measurements = chain()
    result = gate_analysis(receipts, measurements[:-1], authorized=True)
    assert not result.accepted
    assert any("missing" in x for x in result.failures)


def test_measurement_must_match_evidence():
    from dataclasses import replace
    receipts, measurements = chain()
    altered = replace(measurements[0], evidence_digest="f" * 64)
    result = gate_analysis(receipts, (altered,) + measurements[1:],
                           authorized=True)
    assert not result.accepted


def test_calibration_error_has_distinct_threshold():
    from dataclasses import replace
    receipts, measurements = chain()
    altered = tuple(
        replace(x, value=.3) if x.layer is AnalysisLayer.UNCERTAINTY_CALIBRATION else x
        for x in measurements
    )
    assert not gate_analysis(receipts, altered, authorized=True).accepted


def test_gate_requires_authorization():
    receipts, measurements = chain()
    with pytest.raises(PermissionError):
        gate_analysis(receipts, measurements, authorized=False)


def hypothesis():
    return MechanicHypothesis(
        "h-1", "jump_buffering",
        "Input is buffered before landing",
        "Early jump input causes jump on landing",
        "Early input never causes jump on landing",
        "a" * 64,
    )


def test_hypothesis_is_immutable():
    registry = DragonHypothesisRegistry(sqlite3.connect(":memory:"))
    registry.propose("alice", hypothesis(), authorized=True)
    registry.propose("alice", hypothesis(), authorized=True)
    from dataclasses import replace
    with pytest.raises(ValueError, match="conflict"):
        registry.propose("alice", replace(hypothesis(), statement="Different"),
                         authorized=True)


def test_hypothesis_resolution_requires_registration():
    registry = DragonHypothesisRegistry(sqlite3.connect(":memory:"))
    with pytest.raises(ValueError, match="not registered"):
        registry.resolve("alice", HypothesisResult(
            "h-1", HypothesisState.SUPPORTED, "b" * 64, "Trial evidence",
        ), authorized=True)


def test_hypothesis_result_is_immutable():
    registry = DragonHypothesisRegistry(sqlite3.connect(":memory:"))
    registry.propose("alice", hypothesis(), authorized=True)
    result = HypothesisResult(
        "h-1", HypothesisState.REFUTED, "b" * 64, "Not observed",
    )
    registry.resolve("alice", result, authorized=True)
    registry.resolve("alice", result, authorized=True)
    with pytest.raises(ValueError, match="conflict"):
        registry.resolve("alice", HypothesisResult(
            "h-1", HypothesisState.SUPPORTED, "b" * 64, "Changed",
        ), authorized=True)


def test_hypothesis_owner_erasure():
    registry = DragonHypothesisRegistry(sqlite3.connect(":memory:"))
    registry.propose("alice", hypothesis(), authorized=True)
    assert registry.erase("alice", authorized=True) == 1
