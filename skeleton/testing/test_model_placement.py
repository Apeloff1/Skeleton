from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.contracts.canonical import EvidenceRef
from skeleton.network.model_placement import (
    ModelPlacementError,
    ModelPlacementRequest,
    ModelWarmObservation,
    WarmReadiness,
    qualify_model_placement,
    qualify_model_warmup,
)
from skeleton.network.remote_execution import (
    RemoteExecutionGrantDecision,
    RemoteExecutionRequest,
    worker_identity_digest,
)
from skeleton.shells.worker_capacity import (
    CapacityDemand,
    WorkerCapacity,
    WorkerCapacityCatalog,
)
from skeleton.shells.worker_heartbeat import LivenessView, WorkerLiveness
from skeleton.shells.worker_identity import (
    WorkerIdentity,
    WorkerRegistration,
    WorkerRole,
)
from skeleton.shells.worker_reservations import CapacityReservation


NOW = 120.0


def _worker(
    worker_id: str,
    *,
    zone: str,
    boundary: str = "eu",
    generation: int = 1,
) -> WorkerIdentity:
    return WorkerIdentity(
        worker_id=worker_id,
        generation=generation,
        role=WorkerRole.EXECUTOR,
        labels={
            "zone": zone,
            "data_boundary": boundary,
            "accelerator": "cpu",
        },
        features=frozenset({"remote-exec", "model-host"}),
        protocol_version=1,
    )


def _registration(worker: WorkerIdentity) -> WorkerRegistration:
    return WorkerRegistration(
        identity=worker,
        registration_id=f"registration-{worker.worker_id}",
        registered_at=1.0,
        updated_at=2.0,
        enabled=True,
    )


def _live(
    worker: WorkerIdentity,
    *,
    state: WorkerLiveness = WorkerLiveness.HEALTHY,
    inflight: int = 0,
) -> LivenessView:
    return LivenessView(
        worker.worker_id,
        worker.generation,
        state,
        0.1,
        5,
        False,
        inflight,
    )


def _request(**overrides: object) -> ModelPlacementRequest:
    values: dict[str, object] = {
        "placement_id": "placement-1",
        "model_id": "model-a",
        "model_version": "v1",
        "model_digest": "a" * 64,
        "runtime_digest": "b" * 64,
        "tenant_id": "tenant-a",
        "data_class": "internal",
        "allowed_data_boundaries": ("eu",),
        "required_role": WorkerRole.EXECUTOR,
        "required_features": ("model-host",),
        "required_labels": (("accelerator", "cpu"),),
        "topology_label_key": "zone",
        "min_topology_domains": 2,
        "max_topology_skew": 1,
        "demand_inflight": 1,
        "demand_weight": 2,
        "max_worker_inflight": 4,
        "warmup_grant_max_age_s": 30.0,
    }
    values.update(overrides)
    return ModelPlacementRequest(**values)


def _remote_request(
    request: ModelPlacementRequest,
    worker: WorkerIdentity,
    **overrides: object,
) -> RemoteExecutionRequest:
    values: dict[str, object] = {
        "operation_id": "operation-warmup",
        "execution_id": f"warmup-{worker.worker_id}",
        "tenant_id": request.tenant_id,
        "request_id": f"warmup-request-{worker.worker_id}",
        "coordinator_id": "placement-coordinator",
        "action_digest": "c" * 64,
        "authority_digest": "d" * 64,
        "payload_digest": request.warmup_payload_digest,
        "required_role": request.required_role,
        "required_features": ("model-host", "remote-exec"),
        "required_labels": (("accelerator", "cpu"),),
        "protocol_version": 1,
        "max_tokens": 100,
        "max_cost_units": 2.0,
        "max_wall_time_s": 30.0,
    }
    values.update(overrides)
    return RemoteExecutionRequest(**values)


def _grant(
    remote_request: RemoteExecutionRequest,
    worker: WorkerIdentity,
    *,
    accepted: bool = True,
    observed_at: float = 100.0,
) -> RemoteExecutionGrantDecision:
    return RemoteExecutionGrantDecision(
        accepted=accepted,
        reasons=() if accepted else ("forced-rejection",),
        request_digest=remote_request.request_digest,
        worker_identity_digest=worker_identity_digest(worker),
        registration_id=f"registration-{worker.worker_id}",
        heartbeat_sequence=5,
        attestation_digest="e" * 64,
        lease_digest="f" * 64,
        fence_digest="1" * 64,
        fence_epoch=1,
        observed_at=observed_at,
    )


def _warm_pair(
    request: ModelPlacementRequest,
    worker: WorkerIdentity,
    *,
    readiness: WarmReadiness = WarmReadiness.READY,
    expires_at: float = 180.0,
    grant_observed_at: float = 100.0,
):
    remote = _remote_request(request, worker)
    grant = _grant(
        remote,
        worker,
        observed_at=grant_observed_at,
    )
    authorization = qualify_model_warmup(
        request=request,
        remote_request=remote,
        remote_grant=grant,
        worker=worker,
        observed_at=110.0,
    )
    observation = ModelWarmObservation(
        placement_request_digest=request.request_digest,
        authorization_digest=authorization.decision_digest,
        worker_id=worker.worker_id,
        generation=worker.generation,
        worker_identity_digest=worker_identity_digest(worker),
        model_digest=request.model_digest,
        runtime_digest=request.runtime_digest,
        readiness=readiness,
        observed_at=110.0,
        expires_at=expires_at,
        evidence_refs=(
            EvidenceRef(
                source=f"warm://{worker.worker_id}",
                digest="2" * 64,
                category="model_warm_readiness",
            ),
        ),
        verifier_id="verifier:model-warm",
        verifier_digest="3" * 64,
    )
    return remote, grant, authorization, observation


def _fleet_fixture():
    request = _request()
    worker_a = _worker("worker-a", zone="zone-a")
    worker_b = _worker("worker-b", zone="zone-b")
    registrations = (
        _registration(worker_a),
        _registration(worker_b),
    )
    liveness = {
        worker_a.worker_id: _live(worker_a),
        worker_b.worker_id: _live(worker_b),
    }
    capacities = WorkerCapacityCatalog(
        WorkerCapacity(max_inflight=2, max_weight=4)
    )
    warm_a = _warm_pair(request, worker_a)
    warm_b = _warm_pair(request, worker_b)
    authorizations = {
        worker_a.worker_id: warm_a[2],
        worker_b.worker_id: warm_b[2],
    }
    observations = {
        worker_a.worker_id: warm_a[3],
        worker_b.worker_id: warm_b[3],
    }
    reservation = CapacityReservation(
        reservation_id="reservation-b",
        worker=worker_b,
        demand=CapacityDemand(inflight=1, weight=2),
        created_at=100.0,
        expires_at=180.0,
    )
    return (
        request,
        worker_a,
        worker_b,
        registrations,
        liveness,
        capacities,
        authorizations,
        observations,
        reservation,
    )


def test_warmup_authorization_binds_exact_dist01_payload() -> None:
    request = _request()
    worker = _worker("worker-a", zone="zone-a")
    remote = _remote_request(request, worker)
    grant = _grant(remote, worker)

    decision = qualify_model_warmup(
        request=request,
        remote_request=remote,
        remote_grant=grant,
        worker=worker,
        observed_at=110.0,
    )

    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.remote_grant_digest == grant.decision_digest


def test_warmup_payload_substitution_blocks() -> None:
    request = _request()
    worker = _worker("worker-a", zone="zone-a")
    remote = _remote_request(
        request,
        worker,
        payload_digest="0" * 64,
    )
    grant = _grant(remote, worker)

    decision = qualify_model_warmup(
        request=request,
        remote_request=remote,
        remote_grant=grant,
        worker=worker,
        observed_at=110.0,
    )

    assert decision.accepted is False
    assert "warmup-payload-digest-mismatch" in decision.reasons


def test_rejected_or_stale_dist01_grant_blocks_warmup() -> None:
    request = _request()
    worker = _worker("worker-a", zone="zone-a")
    remote = _remote_request(request, worker)

    rejected = qualify_model_warmup(
        request=request,
        remote_request=remote,
        remote_grant=_grant(remote, worker, accepted=False),
        worker=worker,
        observed_at=110.0,
    )
    assert rejected.accepted is False
    assert "remote-grant-rejected" in rejected.reasons

    stale = qualify_model_warmup(
        request=request,
        remote_request=remote,
        remote_grant=_grant(
            remote,
            worker,
            observed_at=50.0,
        ),
        worker=worker,
        observed_at=110.0,
    )
    assert stale.accepted is False
    assert "remote-grant-stale" in stale.reasons


def test_worker_data_boundary_blocks_warmup() -> None:
    request = _request()
    worker = _worker(
        "worker-us",
        zone="zone-us",
        boundary="us",
    )
    remote = _remote_request(request, worker)
    grant = _grant(remote, worker)

    decision = qualify_model_warmup(
        request=request,
        remote_request=remote,
        remote_grant=grant,
        worker=worker,
        observed_at=110.0,
    )

    assert decision.accepted is False
    assert "worker-data-boundary-mismatch" in decision.reasons


def test_topology_and_capacity_select_deterministic_worker() -> None:
    (
        request,
        _,
        worker_b,
        registrations,
        liveness,
        capacities,
        authorizations,
        observations,
        reservation,
    ) = _fleet_fixture()

    decision = qualify_model_placement(
        request=request,
        registrations=registrations,
        liveness=liveness,
        capacities=capacities,
        active_weight={},
        active_assignments={"zone-a": 1, "zone-b": 0},
        warm_authorizations=authorizations,
        warm_observations=observations,
        reservation=reservation,
        observed_at=NOW,
    )

    assert decision.accepted is True
    assert decision.reasons == ()
    assert decision.selected_worker_id == worker_b.worker_id
    assert decision.selected_worker_generation == worker_b.generation
    evidence = decision.accepted_evidence_ref()
    assert evidence.category == "model_placement"
    assert evidence.digest == decision.decision_digest


def test_registration_order_does_not_change_placement_digest() -> None:
    (
        request,
        _,
        _,
        registrations,
        liveness,
        capacities,
        authorizations,
        observations,
        reservation,
    ) = _fleet_fixture()

    left = qualify_model_placement(
        request=request,
        registrations=registrations,
        liveness=liveness,
        capacities=capacities,
        active_weight={},
        active_assignments={"zone-a": 1, "zone-b": 0},
        warm_authorizations=authorizations,
        warm_observations=observations,
        reservation=reservation,
        observed_at=NOW,
    )
    right = qualify_model_placement(
        request=request,
        registrations=tuple(reversed(registrations)),
        liveness=liveness,
        capacities=capacities,
        active_weight={},
        active_assignments={"zone-b": 0, "zone-a": 1},
        warm_authorizations=authorizations,
        warm_observations=observations,
        reservation=reservation,
        observed_at=NOW,
    )

    assert left.accepted is True
    assert right.accepted is True
    assert left.decision_digest == right.decision_digest


def test_device_loss_falls_back_to_other_ready_worker() -> None:
    (
        request,
        worker_a,
        worker_b,
        registrations,
        liveness,
        capacities,
        authorizations,
        observations,
        _,
    ) = _fleet_fixture()
    liveness = {
        **liveness,
        worker_a.worker_id: _live(
            worker_a,
            state=WorkerLiveness.STALE,
        ),
    }
    reservation = CapacityReservation(
        "reservation-b",
        worker_b,
        CapacityDemand(1, 2),
        100.0,
        180.0,
    )

    decision = qualify_model_placement(
        request=request,
        registrations=registrations,
        liveness=liveness,
        capacities=capacities,
        active_weight={},
        active_assignments={"zone-a": 0, "zone-b": 0},
        warm_authorizations=authorizations,
        warm_observations=observations,
        reservation=reservation,
        observed_at=NOW,
    )

    assert decision.accepted is True
    assert decision.selected_worker_id == worker_b.worker_id
    rejected = dict(decision.rejected)
    assert "liveness-stale" in rejected[worker_a.worker_id]


def test_capacity_exhaustion_removes_candidate() -> None:
    (
        request,
        worker_a,
        worker_b,
        registrations,
        liveness,
        capacities,
        authorizations,
        observations,
        _,
    ) = _fleet_fixture()
    capacities.set(
        worker_a.worker_id,
        WorkerCapacity(max_inflight=1, max_weight=1),
    )
    reservation = CapacityReservation(
        "reservation-b",
        worker_b,
        CapacityDemand(1, 2),
        100.0,
        180.0,
    )

    decision = qualify_model_placement(
        request=request,
        registrations=registrations,
        liveness=liveness,
        capacities=capacities,
        active_weight={},
        active_assignments={"zone-a": 0, "zone-b": 0},
        warm_authorizations=authorizations,
        warm_observations=observations,
        reservation=reservation,
        observed_at=NOW,
    )

    assert decision.accepted is True
    assert decision.selected_worker_id == worker_b.worker_id
    assert "capacity-insufficient" in dict(decision.rejected)[
        worker_a.worker_id
    ]


@pytest.mark.parametrize(
    ("readiness", "expires_at", "expected"),
    (
        (WarmReadiness.COLD, 180.0, "warm-readiness-cold"),
        (WarmReadiness.WARMING, 180.0, "warm-readiness-warming"),
        (WarmReadiness.READY, 119.0, "warm-observation-expired"),
    ),
)
def test_unready_or_stale_warm_state_is_not_placeable(
    readiness: WarmReadiness,
    expires_at: float,
    expected: str,
) -> None:
    request = _request(min_topology_domains=1)
    worker = _worker("worker-a", zone="zone-a")
    registration = _registration(worker)
    remote, grant, authorization, observation = _warm_pair(
        request,
        worker,
        readiness=readiness,
        expires_at=expires_at,
    )
    assert remote.request_digest == grant.request_digest
    reservation = CapacityReservation(
        "reservation-a",
        worker,
        CapacityDemand(1, 2),
        100.0,
        180.0,
    )

    decision = qualify_model_placement(
        request=request,
        registrations=(registration,),
        liveness={worker.worker_id: _live(worker)},
        capacities=WorkerCapacityCatalog(
            WorkerCapacity(max_inflight=2, max_weight=4)
        ),
        active_weight={},
        active_assignments={"zone-a": 0},
        warm_authorizations={
            worker.worker_id: authorization,
        },
        warm_observations={
            worker.worker_id: observation,
        },
        reservation=reservation,
        observed_at=NOW,
    )

    assert decision.accepted is False
    assert "no-qualified-placement" in decision.reasons
    assert expected in dict(decision.rejected)[worker.worker_id]


def test_topology_domain_requirement_blocks_single_domain() -> None:
    request = _request(min_topology_domains=2)
    worker = _worker("worker-a", zone="zone-a")
    registration = _registration(worker)
    _, _, authorization, observation = _warm_pair(
        request,
        worker,
    )
    reservation = CapacityReservation(
        "reservation-a",
        worker,
        CapacityDemand(1, 2),
        100.0,
        180.0,
    )

    decision = qualify_model_placement(
        request=request,
        registrations=(registration,),
        liveness={worker.worker_id: _live(worker)},
        capacities=WorkerCapacityCatalog(
            WorkerCapacity(max_inflight=2, max_weight=4)
        ),
        active_weight={},
        active_assignments={"zone-a": 0},
        warm_authorizations={
            worker.worker_id: authorization,
        },
        warm_observations={
            worker.worker_id: observation,
        },
        reservation=reservation,
        observed_at=NOW,
    )

    assert decision.accepted is False
    assert "no-qualified-placement" in decision.reasons


def test_wrong_or_expired_reservation_blocks_final_placement() -> None:
    (
        request,
        worker_a,
        worker_b,
        registrations,
        liveness,
        capacities,
        authorizations,
        observations,
        _,
    ) = _fleet_fixture()

    wrong = CapacityReservation(
        "reservation-a",
        worker_a,
        CapacityDemand(1, 2),
        100.0,
        180.0,
    )
    decision = qualify_model_placement(
        request=request,
        registrations=registrations,
        liveness=liveness,
        capacities=capacities,
        active_weight={},
        active_assignments={"zone-a": 1, "zone-b": 0},
        warm_authorizations=authorizations,
        warm_observations=observations,
        reservation=wrong,
        observed_at=NOW,
    )
    assert decision.accepted is False
    assert "reservation-worker-mismatch" in decision.reasons

    expired = CapacityReservation(
        "reservation-b",
        worker_b,
        CapacityDemand(1, 2),
        100.0,
        119.0,
    )
    decision = qualify_model_placement(
        request=request,
        registrations=registrations,
        liveness=liveness,
        capacities=capacities,
        active_weight={},
        active_assignments={"zone-a": 1, "zone-b": 0},
        warm_authorizations=authorizations,
        warm_observations=observations,
        reservation=expired,
        observed_at=NOW,
    )
    assert decision.accepted is False
    assert "reservation-expired" in decision.reasons


def test_warm_observation_model_substitution_blocks() -> None:
    (
        request,
        _,
        worker_b,
        registrations,
        liveness,
        capacities,
        authorizations,
        observations,
        reservation,
    ) = _fleet_fixture()
    observations = {
        **observations,
        worker_b.worker_id: replace(
            observations[worker_b.worker_id],
            model_digest="0" * 64,
        ),
    }

    decision = qualify_model_placement(
        request=request,
        registrations=registrations,
        liveness=liveness,
        capacities=capacities,
        active_weight={},
        active_assignments={"zone-a": 1, "zone-b": 0},
        warm_authorizations=authorizations,
        warm_observations=observations,
        reservation=reservation,
        observed_at=NOW,
    )

    assert decision.accepted is False
    assert "no-qualified-placement" in decision.reasons
    assert "warm-observation-model-mismatch" in dict(
        decision.rejected
    )[worker_b.worker_id]


def test_rejected_placement_cannot_materialize_promotion_evidence() -> None:
    request = _request(min_topology_domains=1)
    worker = _worker(
        "worker-us",
        zone="zone-us",
        boundary="us",
    )
    _, _, authorization, observation = _warm_pair(
        request,
        worker,
    )
    reservation = CapacityReservation(
        "reservation-us",
        worker,
        CapacityDemand(1, 2),
        100.0,
        180.0,
    )
    decision = qualify_model_placement(
        request=request,
        registrations=(_registration(worker),),
        liveness={worker.worker_id: _live(worker)},
        capacities=WorkerCapacityCatalog(
            WorkerCapacity(max_inflight=2, max_weight=4)
        ),
        active_weight={},
        active_assignments={"zone-us": 0},
        warm_authorizations={
            worker.worker_id: authorization,
        },
        warm_observations={
            worker.worker_id: observation,
        },
        reservation=reservation,
        observed_at=NOW,
    )

    assert decision.accepted is False
    with pytest.raises(
        ModelPlacementError,
        match="cannot become promotion",
    ):
        decision.accepted_evidence_ref()
