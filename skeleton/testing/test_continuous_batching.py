from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.mesh.batching_autoscaling import (
    BatchingAutoscalingError,
    ContinuousBatchItem,
    ContinuousBatchPolicy,
    DispatchDisposition,
    plan_continuous_batch,
)
from skeleton.network.model_placement import (
    ModelPlacementDecision,
    ModelPlacementRequest,
)
from skeleton.shells.worker_identity import WorkerRole


NOW = 100.0


def _placement_request() -> ModelPlacementRequest:
    return ModelPlacementRequest(
        placement_id="placement-1",
        model_id="model-a",
        model_version="v1",
        model_digest="a" * 64,
        runtime_digest="b" * 64,
        tenant_id="tenant-a",
        data_class="internal",
        allowed_data_boundaries=("eu",),
        required_role=WorkerRole.EXECUTOR,
        required_features=("model-host",),
        required_labels=(("accelerator", "cpu"),),
        topology_label_key="zone",
        min_topology_domains=1,
        max_topology_skew=1,
        demand_inflight=1,
        demand_weight=1,
        max_worker_inflight=4,
    )


def _placement(
    request: ModelPlacementRequest,
    *,
    accepted: bool = True,
) -> ModelPlacementDecision:
    return ModelPlacementDecision(
        accepted=accepted,
        reasons=() if accepted else ("forced-rejection",),
        request_digest=request.request_digest,
        selected_worker_id="worker-a" if accepted else None,
        selected_worker_generation=1 if accepted else None,
        selected_worker_identity_digest="c" * 64 if accepted else None,
        warm_authorization_digest="d" * 64 if accepted else None,
        warm_observation_digest="e" * 64 if accepted else None,
        reservation_digest="f" * 64 if accepted else None,
        candidate_worker_ids=("worker-a",) if accepted else (),
        rejected=(),
        topology_digest="1" * 64,
        capacity_digest="2" * 64,
    )


def _policy(**overrides: object) -> ContinuousBatchPolicy:
    values: dict[str, object] = {
        "policy_id": "interactive-v1",
        "max_batch_size": 4,
        "max_wait_s": 5.0,
        "max_batch_runtime_s": 20.0,
        "per_extra_item_overhead_s": 0.5,
    }
    values.update(overrides)
    return ContinuousBatchPolicy(**values)


def _item(
    item_id: str,
    request: ModelPlacementRequest,
    placement: ModelPlacementDecision,
    **overrides: object,
) -> ContinuousBatchItem:
    values: dict[str, object] = {
        "item_id": item_id,
        "tenant_id": request.tenant_id,
        "placement_request_digest": request.request_digest,
        "placement_decision_digest": placement.decision_digest,
        "model_digest": request.model_digest,
        "input_digest": ("3" if item_id.endswith("1") else "4") * 64,
        "quality_policy_digest": "5" * 64,
        "enqueued_at": 90.0,
        "deadline_at": 130.0,
        "estimated_runtime_s": 5.0,
        "cancelled": False,
    }
    values.update(overrides)
    return ContinuousBatchItem(**values)


def test_earliest_deadline_batch_is_ready_and_deterministic() -> None:
    request = _placement_request()
    placement = _placement(request)
    items = (
        _item("item-1", request, placement, deadline_at=125.0),
        _item("item-2", request, placement, deadline_at=120.0),
    )

    left = plan_continuous_batch(
        items=items,
        placement_request=request,
        placement_decision=placement,
        policy=_policy(),
        observed_at=NOW,
    )
    right = plan_continuous_batch(
        items=tuple(reversed(items)),
        placement_request=request,
        placement_decision=placement,
        policy=_policy(),
        observed_at=NOW,
    )

    assert left.accepted is True
    assert left.disposition is DispatchDisposition.READY
    assert left.selected_item_ids == ("item-2", "item-1")
    assert left.decision_digest == right.decision_digest
    evidence = left.accepted_evidence_ref()
    assert evidence.category == "continuous_batch"
    assert evidence.digest == left.decision_digest


def test_cancelled_and_expired_items_are_never_selected() -> None:
    request = _placement_request()
    placement = _placement(request)
    decision = plan_continuous_batch(
        items=(
            _item("item-1", request, placement, cancelled=True),
            _item("item-2", request, placement, deadline_at=99.0),
            _item("item-3", request, placement),
        ),
        placement_request=request,
        placement_decision=placement,
        policy=_policy(),
        observed_at=NOW,
    )

    assert decision.selected_item_ids == ("item-3",)
    rejected = dict(decision.rejected)
    assert "cancelled" in rejected["item-1"]
    assert "deadline-expired" in rejected["item-2"]


def test_adding_item_cannot_make_existing_deadline_infeasible() -> None:
    request = _placement_request()
    placement = _placement(request)
    urgent = _item(
        "item-1",
        request,
        placement,
        deadline_at=106.0,
        estimated_runtime_s=5.0,
    )
    slow = _item(
        "item-2",
        request,
        placement,
        deadline_at=140.0,
        estimated_runtime_s=8.0,
    )
    decision = plan_continuous_batch(
        items=(urgent, slow),
        placement_request=request,
        placement_decision=placement,
        policy=_policy(),
        observed_at=NOW,
    )

    assert decision.selected_item_ids == ("item-1",)
    assert "deadline-infeasible" in dict(decision.rejected)["item-2"]


def test_quality_policy_mixing_is_rejected_from_batch() -> None:
    request = _placement_request()
    placement = _placement(request)
    decision = plan_continuous_batch(
        items=(
            _item("item-1", request, placement),
            _item(
                "item-2",
                request,
                placement,
                quality_policy_digest="6" * 64,
            ),
        ),
        placement_request=request,
        placement_decision=placement,
        policy=_policy(),
        observed_at=NOW,
    )

    assert decision.selected_item_ids == ("item-1",)
    assert "quality-policy-mismatch" in dict(decision.rejected)["item-2"]


@pytest.mark.parametrize(
    ("overrides", "reason"),
    (
        ({"tenant_id": "tenant-b"}, "tenant-mismatch"),
        (
            {"placement_request_digest": "0" * 64},
            "placement-request-mismatch",
        ),
        (
            {"placement_decision_digest": "0" * 64},
            "placement-decision-mismatch",
        ),
        ({"model_digest": "0" * 64}, "model-digest-mismatch"),
    ),
)
def test_item_identity_substitution_is_excluded(
    overrides: dict[str, object],
    reason: str,
) -> None:
    request = _placement_request()
    placement = _placement(request)
    item = _item("item-1", request, placement, **overrides)

    decision = plan_continuous_batch(
        items=(item,),
        placement_request=request,
        placement_decision=placement,
        policy=_policy(),
        observed_at=NOW,
    )

    assert decision.selected_item_ids == ()
    assert reason in dict(decision.rejected)["item-1"]


def test_rejected_or_wrong_placement_blocks_batch_authority() -> None:
    request = _placement_request()
    good = _placement(request)
    rejected = _placement(request, accepted=False)
    item = _item("item-1", request, good)

    decision = plan_continuous_batch(
        items=(item,),
        placement_request=request,
        placement_decision=rejected,
        policy=_policy(),
        observed_at=NOW,
    )

    assert decision.accepted is False
    assert "placement-decision-rejected" in decision.reasons
    assert "placement-decision-mismatch" in dict(decision.rejected)[
        "item-1"
    ]


def test_batch_runtime_budget_excludes_slow_item() -> None:
    request = _placement_request()
    placement = _placement(request)
    decision = plan_continuous_batch(
        items=(
            _item(
                "item-1",
                request,
                placement,
                estimated_runtime_s=25.0,
            ),
        ),
        placement_request=request,
        placement_decision=placement,
        policy=_policy(max_batch_runtime_s=20.0),
        observed_at=NOW,
    )

    assert decision.selected_item_ids == ()
    assert "batch-runtime-budget" in dict(decision.rejected)["item-1"]


def test_not_ready_batch_cannot_be_promotion_evidence() -> None:
    request = _placement_request()
    placement = _placement(request)
    decision = plan_continuous_batch(
        items=(
            _item(
                "item-1",
                request,
                placement,
                enqueued_at=99.5,
                deadline_at=200.0,
            ),
        ),
        placement_request=request,
        placement_decision=placement,
        policy=_policy(max_wait_s=5.0),
        observed_at=NOW,
    )

    assert decision.accepted is True
    assert decision.disposition is DispatchDisposition.WAIT
    with pytest.raises(
        BatchingAutoscalingError,
        match="non-ready batch",
    ):
        decision.accepted_evidence_ref()


def test_duplicate_item_ids_fail_closed() -> None:
    request = _placement_request()
    placement = _placement(request)
    item = _item("item-1", request, placement)
    with pytest.raises(
        BatchingAutoscalingError,
        match="item IDs must be unique",
    ):
        plan_continuous_batch(
            items=(item, item),
            placement_request=request,
            placement_decision=placement,
            policy=_policy(),
            observed_at=NOW,
        )
