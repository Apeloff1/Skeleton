"""Analysis execution planner regression tests."""
import pytest
from skeleton.ai.webcrawler.dragon_analysis_chains import (
    AnalysisLayer, DEFAULT_CHAIN, LayerReceipt,
)
from skeleton.ai.webcrawler.dragon_analysis_execution import (
    WorkerCapability, plan_analysis_execution,
)


def capability(layer):
    return WorkerCapability(layer, f"dragon.worker.{layer.value}", "1", True)


def first_receipt():
    return LayerReceipt(
        AnalysisLayer.SOURCE_INTEGRITY, (), "a" * 64, 1, True,
    )


def test_first_layer_ready_only_when_worker_exists():
    empty = plan_analysis_execution((), (), authorized=True)
    assert not empty.ready
    result = plan_analysis_execution(
        (), (capability(AnalysisLayer.SOURCE_INTEGRITY),),
        authorized=True,
    )
    assert len(result.ready) == 1
    assert result.ready[0].layer is AnalysisLayer.SOURCE_INTEGRITY


def test_downstream_requires_verified_evidence():
    result = plan_analysis_execution(
        (first_receipt(),),
        (capability(AnalysisLayer.TEMPORAL_SEGMENTATION),),
        authorized=True,
    )
    assert len(result.ready) == 1
    assert result.ready[0].input_fingerprints == ("a" * 64,)


def test_missing_worker_fails_closed():
    result = plan_analysis_execution(
        (first_receipt(),), (), authorized=True,
    )
    assert not result.ready
    assert any(
        layer is AnalysisLayer.TEMPORAL_SEGMENTATION and
        "no executable" in reason
        for layer, reason in result.blocked
    )


def test_rejected_receipt_cannot_unlock_descendants():
    bad = LayerReceipt(
        AnalysisLayer.SOURCE_INTEGRITY, (), "a" * 64, 1, False,
    )
    result = plan_analysis_execution(
        (bad,),
        (capability(AnalysisLayer.TEMPORAL_SEGMENTATION),),
        authorized=True,
    )
    assert not result.ready
    assert AnalysisLayer.SOURCE_INTEGRITY not in result.completed


def test_duplicate_worker_registration_rejected():
    cap = capability(AnalysisLayer.SOURCE_INTEGRITY)
    with pytest.raises(ValueError, match="duplicate"):
        plan_analysis_execution(
            (), (cap, cap), authorized=True,
        )


def test_dispatch_budget_validated():
    with pytest.raises(ValueError, match="budget"):
        plan_analysis_execution(
            (), (), authorized=True, max_dispatch=0,
        )


def test_authorization_required():
    with pytest.raises(PermissionError):
        plan_analysis_execution(
            (), (), authorized=False,
        )
