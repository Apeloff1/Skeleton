from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

from skeleton.contracts.canonical import EvidenceRef, canonical_json_bytes
from skeleton.distributed.network.hardware_topology import (
    DeviceDescriptor,
    DeviceKind,
    HardwareTopologySnapshot,
    WorkerHardwareObservation,
    collect_hardware_topology,
)
from skeleton.distributed.network.model_placement import (
    ModelPlacementRequest,
    ModelWarmObservation,
    WarmReadiness,
    qualify_model_warmup,
    select_model_placement,
)
from skeleton.distributed.network.placement_scheduler import (
    HardwareRequirement,
    PlacementSchedulerError,
    schedule_model_placement,
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
from skeleton.shells.worker_heartbeat import (
    HeartbeatPolicy,
    HeartbeatRegistry,
)
from skeleton.shells.worker_identity import (
    WorkerIdentity,
    WorkerIdentityError,
    WorkerRegistry,
    WorkerRole,
)
from skeleton.shells.worker_reservations import (
    ReservationConflict,
    WorkerReservations,
)


class Clock:
    def __init__(self, value: float = 120.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _worker(worker_id: str, zone: str, *, generation: int = 1) -> WorkerIdentity:
    return WorkerIdentity(
        worker_id=worker_id,
        generation=generation,
        role=WorkerRole.EXECUTOR,
        labels={
            "zone": zone,
            "rack": f"rack-{zone[-1]}",
            "data_boundary": "eu",
            "accelerator": "gpu",
        },
        features=frozenset({"remote-exec", "model-host"}),
        protocol_version=1,
    )


def _request() -> ModelPlacementRequest:
    return ModelPlacementRequest(
        placement_id="placement-vol031",
        model_id="model-a",
        model_version="v1",
        model_digest="a" * 64,
        runtime_digest="b" * 64,
        tenant_id="tenant-a",
        data_class="internal",
        allowed_data_boundaries=("eu",),
        required_role=WorkerRole.EXECUTOR,
        required_features=("model-host",),
        required_labels=(("accelerator", "gpu"),),
        topology_label_key="zone",
        min_topology_domains=2,
        max_topology_skew=1,
        demand_inflight=1,
        demand_weight=2,
        max_worker_inflight=4,
        warmup_grant_max_age_s=30.0,
    )


def _remote(
    request: ModelPlacementRequest,
    worker: WorkerIdentity,
) -> RemoteExecutionRequest:
    return RemoteExecutionRequest(
        operation_id=f"warm-{worker.worker_id}",
        execution_id=f"exec-{worker.worker_id}",
        tenant_id=request.tenant_id,
        request_id=f"request-{worker.worker_id}",
        coordinator_id="placement-coordinator",
        action_digest="c" * 64,
        authority_digest="d" * 64,
        payload_digest=request.warmup_payload_digest,
        required_role=request.required_role,
        required_features=("model-host", "remote-exec"),
        required_labels=(("accelerator", "gpu"),),
        protocol_version=1,
        max_tokens=100,
        max_cost_units=2.0,
        max_wall_time_s=30.0,
    )


def _warm(
    request: ModelPlacementRequest,
    worker: WorkerIdentity,
    *,
    observed_at: float = 110.0,
):
    remote = _remote(request, worker)
    grant = RemoteExecutionGrantDecision(
        accepted=True,
        reasons=(),
        request_digest=remote.request_digest,
        worker_identity_digest=worker_identity_digest(worker),
        registration_id=f"registration-{worker.worker_id}",
        heartbeat_sequence=1,
        attestation_digest="e" * 64,
        lease_digest="f" * 64,
        fence_digest="1" * 64,
        fence_epoch=1,
        observed_at=100.0,
    )
    authorization = qualify_model_warmup(
        request=request,
        remote_request=remote,
        remote_grant=grant,
        worker=worker,
        observed_at=observed_at,
    )
    observation = ModelWarmObservation(
        placement_request_digest=request.request_digest,
        authorization_digest=authorization.decision_digest,
        worker_id=worker.worker_id,
        generation=worker.generation,
        worker_identity_digest=worker_identity_digest(worker),
        model_digest=request.model_digest,
        runtime_digest=request.runtime_digest,
        readiness=WarmReadiness.READY,
        observed_at=observed_at,
        expires_at=180.0,
        evidence_refs=(
            EvidenceRef(
                source=f"hardware-warm://{worker.worker_id}",
                digest="2" * 64,
                category="model_warm_readiness",
            ),
        ),
        verifier_id="verifier:model-warm",
        verifier_digest="3" * 64,
    )
    return authorization, observation


def _hardware(
    worker: WorkerIdentity,
    *,
    observed_at: float = 115.0,
    ram_bytes: int = 64 * 1024**3,
    accelerator_bytes: int = 24 * 1024**3,
) -> WorkerHardwareObservation:
    return WorkerHardwareObservation(
        worker_id=worker.worker_id,
        generation=worker.generation,
        cpu_logical_cores=32,
        cpu_physical_cores=16,
        ram_bytes=ram_bytes,
        storage_free_bytes=500 * 1024**3,
        network_mbps=25000.0,
        numa_nodes=2,
        devices=(
            DeviceDescriptor(
                device_id=f"gpu-{worker.worker_id}",
                kind=DeviceKind.GPU,
                model="accelerator-a",
                memory_bytes=accelerator_bytes,
                compute_units=128,
                numa_node=0,
                healthy=True,
            ),
        ),
        topology=(
            ("data_boundary", "eu"),
            ("rack", worker.labels["rack"]),
            ("zone", worker.labels["zone"]),
        ),
        observed_at=observed_at,
        source_digest="4" * 64,
    )


def _fixture():
    clock = Clock()
    workers = WorkerRegistry(clock=clock)
    worker_a = _worker("worker-a", "zone-a")
    worker_b = _worker("worker-b", "zone-b")
    reg_a = workers.register(worker_a)
    reg_b = workers.register(worker_b)
    heartbeats = HeartbeatRegistry(
        workers=workers,
        policy=HeartbeatPolicy(
            late_after_seconds=10.0,
            stale_after_seconds=20.0,
        ),
        clock=clock,
    )
    heartbeats.beat(worker_a, sequence=1)
    heartbeats.beat(worker_b, sequence=1)
    capacities = WorkerCapacityCatalog(
        WorkerCapacity(max_inflight=2, max_weight=4)
    )
    reservations = WorkerReservations(
        workers,
        heartbeats,
        capacities,
        clock=clock,
    )
    request = _request()
    warm_a = _warm(request, worker_a)
    warm_b = _warm(request, worker_b)
    registrations = (reg_a, reg_b)
    liveness = {
        worker_a.worker_id: heartbeats.liveness(worker_a),
        worker_b.worker_id: heartbeats.liveness(worker_b),
    }
    authorizations = {
        worker_a.worker_id: warm_a[0],
        worker_b.worker_id: warm_b[0],
    }
    observations = {
        worker_a.worker_id: warm_a[1],
        worker_b.worker_id: warm_b[1],
    }
    hardware = {
        worker_a.worker_id: _hardware(worker_a),
        worker_b.worker_id: _hardware(worker_b),
    }
    topology = collect_hardware_topology(
        registrations=registrations,
        observations=hardware,
        observed_at=clock(),
        max_age_s=30.0,
    )
    return {
        "clock": clock,
        "workers": workers,
        "worker_a": worker_a,
        "worker_b": worker_b,
        "registrations": registrations,
        "heartbeats": heartbeats,
        "liveness": liveness,
        "capacities": capacities,
        "reservations": reservations,
        "request": request,
        "authorizations": authorizations,
        "observations": observations,
        "hardware": hardware,
        "topology": topology,
    }


def _requirement(**overrides) -> HardwareRequirement:
    values = {
        "min_logical_cores": 16,
        "min_ram_bytes": 32 * 1024**3,
        "min_storage_free_bytes": 100 * 1024**3,
        "min_network_mbps": 10000.0,
        "min_accelerator_memory_bytes": 16 * 1024**3,
        "min_numa_nodes": 1,
    }
    values.update(overrides)
    return HardwareRequirement(**values)


def _schedule(fixture, **overrides):
    values = {
        "request": fixture["request"],
        "registrations": fixture["registrations"],
        "liveness": fixture["liveness"],
        "capacities": fixture["capacities"],
        "active_weight": {},
        "active_assignments": {"zone-a": 1, "zone-b": 0},
        "warm_authorizations": fixture["authorizations"],
        "warm_observations": fixture["observations"],
        "hardware_snapshot": fixture["topology"],
        "hardware_requirement": _requirement(),
        "reservations": fixture["reservations"],
        "observed_at": fixture["clock"](),
        "reservation_ttl_s": 30.0,
    }
    values.update(overrides)
    return schedule_model_placement(**values)


def test_hardware_collector_binds_exact_worker_generation_and_topology() -> None:
    fixture = _fixture()
    snapshot = fixture["topology"]

    assert [item.worker_id for item in snapshot.observations] == [
        "worker-a",
        "worker-b",
    ]
    assert snapshot.rejected == ()
    assert snapshot.by_worker()["worker-a"].generation == 1
    assert dict(snapshot.by_worker()["worker-a"].topology)["zone"] == "zone-a"


def test_hardware_snapshot_identity_uses_shared_canonical_bytes() -> None:
    snapshot = _fixture()["topology"]

    assert snapshot.snapshot_digest == hashlib.sha256(
        canonical_json_bytes(snapshot.payload())
    ).hexdigest()


def test_hardware_collector_rejects_stale_generation() -> None:
    fixture = _fixture()
    stale = replace(
        fixture["hardware"]["worker-a"],
        generation=2,
    )

    snapshot = collect_hardware_topology(
        registrations=fixture["registrations"],
        observations={
            **fixture["hardware"],
            "worker-a": stale,
        },
        observed_at=fixture["clock"](),
        max_age_s=30.0,
    )

    rejected = dict(snapshot.rejected)
    assert "hardware-generation-mismatch" in rejected["worker-a"]
    assert "worker-a" not in snapshot.by_worker()


def test_hardware_collector_rejects_stale_observation() -> None:
    fixture = _fixture()
    old = _hardware(
        fixture["worker_a"],
        observed_at=80.0,
    )

    snapshot = collect_hardware_topology(
        registrations=fixture["registrations"],
        observations={
            **fixture["hardware"],
            "worker-a": old,
        },
        observed_at=fixture["clock"](),
        max_age_s=30.0,
    )

    assert "hardware-observation-stale" in dict(snapshot.rejected)["worker-a"]


def test_hardware_collector_rejects_label_topology_drift() -> None:
    fixture = _fixture()
    worker = fixture["worker_a"]
    drift = WorkerHardwareObservation(
        worker_id=worker.worker_id,
        generation=worker.generation,
        cpu_logical_cores=32,
        cpu_physical_cores=16,
        ram_bytes=64 * 1024**3,
        storage_free_bytes=500 * 1024**3,
        network_mbps=25000.0,
        numa_nodes=2,
        devices=_hardware(worker).devices,
        topology=(
            ("data_boundary", "eu"),
            ("rack", worker.labels["rack"]),
            ("zone", "zone-b"),
        ),
        observed_at=115.0,
        source_digest="4" * 64,
    )

    snapshot = collect_hardware_topology(
        registrations=fixture["registrations"],
        observations={
            **fixture["hardware"],
            worker.worker_id: drift,
        },
        observed_at=fixture["clock"](),
        max_age_s=30.0,
    )

    assert "hardware-topology-zone-mismatch" in dict(snapshot.rejected)[
        worker.worker_id
    ]


def test_scheduler_selects_then_reserves_exact_worker() -> None:
    fixture = _fixture()

    receipt, reservation = _schedule(fixture)

    assert receipt.accepted is True
    assert reservation is not None
    assert reservation.worker.worker_id == "worker-b"
    assert reservation.worker.generation == receipt.selected_worker_generation
    assert reservation.demand == fixture["request"].demand
    assert fixture["reservations"].require(reservation) == reservation
    assert receipt.reservation_id == reservation.reservation_id
    assert receipt.authority_scope == "capacity-reservation-only"
    assert receipt.production_authority is False


def test_scheduler_selection_matches_pure_selection_phase() -> None:
    fixture = _fixture()
    selection = select_model_placement(
        request=fixture["request"],
        registrations=fixture["registrations"],
        liveness=fixture["liveness"],
        capacities=fixture["capacities"],
        active_weight={},
        active_assignments={"zone-a": 1, "zone-b": 0},
        warm_authorizations=fixture["authorizations"],
        warm_observations=fixture["observations"],
        observed_at=fixture["clock"](),
    )

    receipt, reservation = _schedule(fixture)

    assert receipt.accepted is True
    assert reservation is not None
    assert receipt.selected_worker_id == selection.selected_worker_id
    assert receipt.selection_digest == selection.selection_digest


def test_insufficient_hardware_denies_before_reservation_mutation() -> None:
    fixture = _fixture()

    receipt, reservation = _schedule(
        fixture,
        hardware_requirement=_requirement(
            min_accelerator_memory_bytes=80 * 1024**3,
        ),
    )

    assert receipt.accepted is False
    assert reservation is None
    assert "hardware-accelerator-memory-insufficient" in receipt.reasons
    assert fixture["reservations"].snapshot() == ()


def test_stale_hardware_snapshot_denies_before_reservation() -> None:
    fixture = _fixture()
    fixture["clock"].advance(31.0)

    receipt, reservation = _schedule(
        fixture,
        observed_at=fixture["clock"](),
    )

    assert receipt.accepted is False
    assert reservation is None
    assert "hardware-snapshot-stale" in receipt.reasons
    assert fixture["reservations"].snapshot() == ()


def test_hardware_registration_snapshot_mismatch_fails_closed() -> None:
    fixture = _fixture()
    forged = HardwareTopologySnapshot(
        observed_at=fixture["topology"].observed_at,
        max_age_s=fixture["topology"].max_age_s,
        observations=fixture["topology"].observations,
        rejected=fixture["topology"].rejected,
        registration_digest="0" * 64,
    )

    receipt, reservation = _schedule(
        fixture,
        hardware_snapshot=forged,
    )

    assert receipt.accepted is False
    assert reservation is None
    assert "hardware-registration-snapshot-mismatch" in receipt.reasons


def test_real_reservation_capacity_conflict_denies_schedule() -> None:
    fixture = _fixture()
    worker_b = fixture["worker_b"]
    blocker = fixture["reservations"].reserve(
        worker_b,
        CapacityDemand(inflight=2, weight=4),
        ttl_seconds=30.0,
    )

    receipt, reservation = _schedule(fixture)

    assert receipt.accepted is False
    assert reservation is None
    assert any(reason.startswith("reservation-conflict:") for reason in receipt.reasons)
    assert fixture["reservations"].require(blocker) == blocker


def test_scheduler_receipt_identity_uses_shared_canonical_bytes() -> None:
    fixture = _fixture()
    receipt, reservation = _schedule(fixture)

    assert receipt.accepted is True
    assert reservation is not None
    assert receipt.receipt_digest == hashlib.sha256(
        canonical_json_bytes(receipt.payload())
    ).hexdigest()


def test_rejected_scheduler_receipt_cannot_claim_execution_authority() -> None:
    fixture = _fixture()
    receipt, _ = _schedule(
        fixture,
        hardware_requirement=_requirement(
            min_ram_bytes=128 * 1024**3,
        ),
    )
    assert receipt.accepted is False

    with pytest.raises(PlacementSchedulerError, match="scope escalation"):
        type(receipt)(
            accepted=False,
            reasons=receipt.reasons,
            request_digest=receipt.request_digest,
            selection_digest=receipt.selection_digest,
            hardware_requirement_digest=receipt.hardware_requirement_digest,
            hardware_snapshot_digest=receipt.hardware_snapshot_digest,
            hardware_observation_digest=receipt.hardware_observation_digest,
            reservation_id=receipt.reservation_id,
            reservation_digest=receipt.reservation_digest,
            placement_decision_digest=receipt.placement_decision_digest,
            selected_worker_id=receipt.selected_worker_id,
            selected_worker_generation=receipt.selected_worker_generation,
            reservation_expires_at=receipt.reservation_expires_at,
            authority_scope="execute-model",
        )


def test_vol031_canonical_and_ai_mirrors_are_byte_identical() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    pairs = (
        (
            root / "skeleton/distributed/network/hardware_topology.py",
            root / "skeleton/ai/runtime/distributed/network/hardware_topology.py",
        ),
        (
            root / "skeleton/distributed/network/placement_scheduler.py",
            root / "skeleton/ai/runtime/distributed/network/placement_scheduler.py",
        ),
        (
            root / "skeleton/distributed/network/model_placement.py",
            root / "skeleton/ai/runtime/distributed/network/model_placement.py",
        ),
    )
    for source, mirror in pairs:
        assert source.read_bytes() == mirror.read_bytes()



def test_worker_generation_race_becomes_fail_closed_receipt(monkeypatch) -> None:
    fixture = _fixture()

    def stale_reserve(*args, **kwargs):
        raise WorkerIdentityError("worker generation is stale")

    monkeypatch.setattr(
        fixture["reservations"],
        "reserve",
        stale_reserve,
    )
    receipt, reservation = _schedule(fixture)

    assert receipt.accepted is False
    assert reservation is None
    assert "reservation-conflict:WorkerIdentityError" in receipt.reasons
