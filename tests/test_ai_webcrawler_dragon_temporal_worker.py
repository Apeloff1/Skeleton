"""Regression coverage for executable temporal analysis worker."""
import pytest

from skeleton.ai.webcrawler.dragon_analysis_chains import (
    AnalysisLayer, LayerReceipt, validate_chain,
)
from skeleton.ai.webcrawler.dragon_analysis_execution import LayerDispatch
from skeleton.ai.webcrawler.dragon_temporal_segmentation import FeatureFrame
from skeleton.ai.webcrawler.dragon_temporal_worker import execute_temporal_dispatch


def source():
    return LayerReceipt(
        AnalysisLayer.SOURCE_INTEGRITY, (), "a" * 64, 1, True,
    )


def dispatch():
    return LayerDispatch(
        AnalysisLayer.TEMPORAL_SEGMENTATION, ("a" * 64,),
        "dragon.temporal", "1",
    )


def frames():
    return tuple(FeatureFrame(
        i * 100, (0.1 if i < 10 else 0.9,), f"frame-{i}",
    ) for i in range(16))


def test_worker_emits_evidence_bound_receipt():
    result = execute_temporal_dispatch(
        dispatch(), frames(), authorized=True,
        source_integrity_receipt=source(),
    )
    assert result.frame_count == 16
    assert result.event_count >= 1
    assert result.receipt.input_fingerprints == ("a" * 64,)
    assert result.receipt.passed
    assert len(result.receipt.output_fingerprint) == 64


def test_worker_deterministic():
    first = execute_temporal_dispatch(
        dispatch(), frames(), authorized=True,
        source_integrity_receipt=source(),
    )
    second = execute_temporal_dispatch(
        dispatch(), frames(), authorized=True,
        source_integrity_receipt=source(),
    )
    assert first == second


def test_worker_rejects_stale_input_digest():
    stale = LayerDispatch(
        AnalysisLayer.TEMPORAL_SEGMENTATION, ("b" * 64,),
        "dragon.temporal", "1",
    )
    with pytest.raises(ValueError, match="does not match"):
        execute_temporal_dispatch(
            stale, frames(), authorized=True,
            source_integrity_receipt=source(),
        )


def test_worker_rejects_wrong_layer():
    wrong = LayerDispatch(
        AnalysisLayer.OBJECT_TRACKING, ("a" * 64,),
        "dragon.temporal", "1",
    )
    with pytest.raises(ValueError, match="another"):
        execute_temporal_dispatch(
            wrong, frames(), authorized=True,
            source_integrity_receipt=source(),
        )


def test_worker_requires_consent():
    with pytest.raises(PermissionError):
        execute_temporal_dispatch(
            dispatch(), frames(), authorized=False,
            source_integrity_receipt=source(),
        )


def test_worker_cannot_certify_empty_frames():
    result = execute_temporal_dispatch(
        dispatch(), (), authorized=True,
        source_integrity_receipt=source(),
    )
    assert not result.receipt.passed


def test_worker_receipt_is_valid_in_chain():
    result = execute_temporal_dispatch(
        dispatch(), frames(), authorized=True,
        source_integrity_receipt=source(),
    )
    verdict = validate_chain(
        (source(), result.receipt), authorized=True,
    )
    assert AnalysisLayer.TEMPORAL_SEGMENTATION in verdict.accepted_layers
