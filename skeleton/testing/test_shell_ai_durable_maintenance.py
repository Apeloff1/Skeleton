"""Fenced durable maintenance epoch safety and fault-injection tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    FencedLease,
    InMemoryFencedStore,
    LeaseConflict,
)
from skeleton.shells.ai.durable_maintenance import (
    GENESIS_ROOT,
    MAINTENANCE_ARTIFACT_TYPE,
    DurableMaintenanceClaim,
    DurableMaintenanceConflict,
    DurableMaintenanceEpoch,
    DurableMaintenanceGuard,
    DurableMaintenanceOperation,
    DurableMaintenancePolicy,
    DurableMaintenanceRecord,
    DurableMaintenanceResource,
    DurableMaintenanceStale,
    DurableMaintenanceState,
    DurableMaintenanceStore,
    SignedDurableMaintenanceEpoch,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSigner,
    SignedArtifact,
)


def fp(char: str) -> str:
    return char * 64


def resource(
    name: str,
    *,
    kind: str = "evidence-chain",
    sequence: int = 10,
    root: str | None = None,
    state: str | None = None,
) -> DurableMaintenanceResource:
    if sequence == 0:
        root = GENESIS_ROOT
    return DurableMaintenanceResource(
        name,
        kind,
        sequence,
        root or fp(name[0].lower()),
        state or fp("s"),
    )


class Clock:
    def __init__(self, value: float = 100.0):
        self.value = value

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class NonceFactory:
    def __init__(self):
        self.value = 0

    def __call__(self) -> str:
        self.value += 1
        return f"nonce-{self.value}"


def environment(
    *,
    policy: DurableMaintenancePolicy | None = None,
    backend=None,
    clock: Clock | None = None,
):
    clock = clock or Clock()
    backend = backend or InMemoryFencedStore(
        clock=clock,
    )
    signer = ArtifactSigner(
        "maintenance",
        b"k" * 32,
        clock=clock,
    )
    store = DurableMaintenanceStore(
        backend,
        signer,
        policy=policy,
        namespace="maintenance",
        clock=clock,
        nonce_factory=NonceFactory(),
    )
    return clock, backend, signer, store


def acquire(
    store: DurableMaintenanceStore,
    *,
    operation=DurableMaintenanceOperation.COMPACTION,
    owner="operator",
    resources=None,
    ttl=60.0,
):
    return store.acquire(
        operation,
        owner_id=owner,
        resources=resources
        or (
            resource("journal", root=fp("a")),
            resource("receipts", root=fp("b")),
        ),
        ttl_seconds=ttl,
    )


def test_acquire_multi_resource_epoch_is_signed_and_active():
    _, backend, signer, store = environment()
    signed = acquire(store)
    assert isinstance(
        signed,
        SignedDurableMaintenanceEpoch,
    )
    signer.verify(signed.signature)
    assert (
        signed.signature.artifact_type
        == MAINTENANCE_ARTIFACT_TYPE
    )
    assert (
        signed.signature.artifact_digest
        == signed.epoch.digest
    )
    assert signed.epoch.operation is (
        DurableMaintenanceOperation.COMPACTION
    )
    assert signed.epoch.resource_ids == (
        "journal",
        "receipts",
    )
    assert len(signed.epoch.claims) == 2
    assert len(backend.leases()) == 2

    status = store.require_active(
        signed,
        operation=(
            DurableMaintenanceOperation.COMPACTION
        ),
        required_resources=("journal", "receipts"),
    )
    assert status.active
    assert status.destructive_action_authorized
    assert status.reasons == ()


def test_acquire_sorts_resources_before_locking():
    _, _, _, store = environment()
    signed = acquire(
        store,
        resources=(
            resource("zeta", root=fp("z")),
            resource("alpha", root=fp("a")),
            resource("middle", root=fp("m")),
        ),
    )
    assert signed.epoch.resource_ids == (
        "alpha",
        "middle",
        "zeta",
    )
    assert tuple(
        claim.resource_id
        for claim in signed.epoch.claims
    ) == signed.epoch.resource_ids


def test_overlapping_epoch_is_rejected():
    _, _, _, store = environment()
    first = acquire(
        store,
        owner="first",
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    assert store.require_active(first).active
    with pytest.raises(
        DurableMaintenanceConflict,
        match="active authority",
    ):
        acquire(
            store,
            owner="second",
            operation=(
                DurableMaintenanceOperation.FAILOVER
            ),
            resources=(
                resource("journal", root=fp("a")),
            ),
        )


def test_disjoint_epochs_can_coexist():
    _, backend, _, store = environment()
    first = acquire(
        store,
        owner="first",
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    second = acquire(
        store,
        owner="second",
        operation=(
            DurableMaintenanceOperation.FAILOVER
        ),
        resources=(
            resource("receipts", root=fp("b")),
        ),
    )
    assert store.require_active(first).active
    assert store.require_active(second).active
    assert len(backend.leases()) == 2


def test_release_frees_resources_for_new_epoch():
    _, _, _, store = environment()
    first = acquire(
        store,
        owner="first",
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    first_token = (
        first.epoch.claims[0].fencing_token
    )
    released = store.release(
        first,
        owner_id="first",
    )
    assert (
        released.state
        is DurableMaintenanceState.RELEASED
    )
    assert not store.inspect(first).active

    second = acquire(
        store,
        owner="second",
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    assert (
        second.epoch.claims[0].fencing_token
        > first_token
    )


def test_release_is_idempotent_after_success():
    _, backend, _, store = environment()
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    first = store.release(signed)
    second = store.release(signed)
    assert second == first
    assert len(backend.leases()) == 0


def test_release_owner_mismatch_is_rejected():
    _, _, _, store = environment()
    signed = acquire(
        store,
        owner="correct",
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    with pytest.raises(
        DurableMaintenanceConflict,
        match="owner mismatch",
    ):
        store.release(
            signed,
            owner_id="wrong",
        )


def test_operation_mismatch_is_fail_closed():
    _, _, _, store = environment()
    signed = acquire(
        store,
        operation=(
            DurableMaintenanceOperation.PRUNING
        ),
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    status = store.inspect(
        signed,
        operation=(
            DurableMaintenanceOperation.FAILOVER
        ),
    )
    assert not status.active
    assert not status.operation_valid
    with pytest.raises(
        DurableMaintenanceStale,
        match="operation differs",
    ):
        store.require_active(
            signed,
            operation=(
                DurableMaintenanceOperation.FAILOVER
            ),
        )


def test_required_resource_subset_is_enforced():
    _, _, _, store = environment()
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    status = store.inspect(
        signed,
        required_resources=(
            "journal",
            "receipts",
        ),
    )
    assert not status.resources_valid
    with pytest.raises(
        DurableMaintenanceStale,
        match="lacks required resources",
    ):
        store.require_active(
            signed,
            required_resources=(
                "receipts",
            ),
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("sequence", 11),
        ("root_hash", fp("c")),
        ("state_digest", fp("d")),
        ("resource_kind", "other-kind"),
    ],
)
def test_live_resource_state_drift_invalidates_epoch(
    field,
    value,
):
    _, _, _, store = environment()
    original = resource(
        "journal",
        root=fp("a"),
        state=fp("s"),
    )
    signed = acquire(
        store,
        resources=(original,),
    )
    drifted = replace(
        original,
        **{field: value},
    )
    status = store.inspect(
        signed,
        live_resources=(drifted,),
    )
    assert not status.live_state_valid
    assert not status.active
    with pytest.raises(
        DurableMaintenanceStale,
        match="state changed",
    ):
        store.require_active(
            signed,
            live_resources=(drifted,),
        )


def test_unmentioned_live_resource_does_not_change_binding():
    _, _, _, store = environment()
    original = resource(
        "journal",
        root=fp("a"),
    )
    signed = acquire(
        store,
        resources=(original,),
    )
    status = store.require_active(
        signed,
        live_resources=(
            resource(
                "other",
                root=fp("b"),
            ),
        ),
    )
    assert status.active


def test_policy_drift_invalidates_epoch():
    clock, backend, signer, first_store = (
        environment()
    )
    signed = acquire(
        first_store,
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    second_store = DurableMaintenanceStore(
        backend,
        signer,
        policy=DurableMaintenancePolicy(
            max_resources=8,
        ),
        namespace="maintenance",
        clock=clock,
        nonce_factory=NonceFactory(),
    )
    status = second_store.inspect(signed)
    assert not status.policy_valid
    assert not status.active
    with pytest.raises(
        DurableMaintenanceStale,
        match="policy digest changed",
    ):
        second_store.require_active(signed)


def test_expiry_invalidates_epoch_and_backend_lease():
    clock, backend, _, store = environment()
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
        ),
        ttl=5.0,
    )
    clock.advance(6.0)
    status = store.inspect(signed)
    assert not status.time_valid
    assert not status.leases_valid
    assert not status.active
    assert len(backend.leases()) == 0


def test_mark_expired_persists_terminal_state():
    clock, _, _, store = environment()
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
        ),
        ttl=5.0,
    )
    clock.advance(6.0)
    record = store.mark_expired(signed)
    assert (
        record.state
        is DurableMaintenanceState.EXPIRED
    )
    stored = store.get(signed.epoch_id)
    assert stored is not None
    assert (
        stored.record.state
        is DurableMaintenanceState.EXPIRED
    )


def test_mark_expired_before_deadline_is_rejected():
    _, _, _, store = environment()
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    with pytest.raises(
        DurableMaintenanceConflict,
        match="has not expired",
    ):
        store.mark_expired(signed)


def test_renew_supersedes_parent_and_keeps_fencing_tokens():
    clock, _, _, store = environment()
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
            resource("receipts", root=fp("b")),
        ),
        ttl=20.0,
    )
    old_tokens = tuple(
        claim.fencing_token
        for claim in signed.epoch.claims
    )
    old_expiry = signed.epoch.expires_at
    clock.advance(5.0)
    renewed = store.renew(
        signed,
        ttl_seconds=30.0,
    )
    assert (
        renewed.epoch.parent_epoch_id
        == signed.epoch_id
    )
    assert renewed.epoch.renewal_count == 1
    assert (
        tuple(
            claim.fencing_token
            for claim in renewed.epoch.claims
        )
        == old_tokens
    )
    assert renewed.epoch.expires_at > old_expiry
    assert store.require_active(renewed).active

    old = store.get(signed.epoch_id)
    assert old is not None
    assert (
        old.record.state
        is DurableMaintenanceState.SUPERSEDED
    )
    assert (
        old.record.replacement_epoch_id
        == renewed.epoch_id
    )
    with pytest.raises(
        DurableMaintenanceStale,
    ):
        store.require_active(signed)


def test_superseded_parent_cannot_release_renewed_leases():
    clock, backend, _, store = environment()
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    clock.advance(1.0)
    renewed = store.renew(signed)
    with pytest.raises(
        DurableMaintenanceConflict,
        match="superseded",
    ):
        store.release(signed)
    assert len(backend.leases()) == 1
    assert store.require_active(renewed).active


def test_renewal_limit_is_enforced():
    policy = DurableMaintenancePolicy(
        max_renewals=1,
    )
    clock, _, _, store = environment(
        policy=policy,
    )
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    clock.advance(1.0)
    renewed = store.renew(signed)
    clock.advance(1.0)
    with pytest.raises(
        DurableMaintenanceConflict,
        match="renewal limit",
    ):
        store.renew(renewed)


def test_renewal_live_state_drift_is_rejected_before_renew():
    clock, _, _, store = environment()
    original = resource(
        "journal",
        root=fp("a"),
    )
    signed = acquire(
        store,
        resources=(original,),
    )
    clock.advance(1.0)
    with pytest.raises(
        DurableMaintenanceStale,
        match="state changed",
    ):
        store.renew(
            signed,
            live_resources=(
                replace(
                    original,
                    sequence=11,
                ),
            ),
        )


class FailSecondRenewBackend:
    def __init__(self, clock):
        self.inner = InMemoryFencedStore(
            clock=clock,
        )
        self.renew_count = 0

    def get(self, *args, **kwargs):
        return self.inner.get(*args, **kwargs)

    def put_if_absent(self, *args, **kwargs):
        return self.inner.put_if_absent(
            *args,
            **kwargs,
        )

    def compare_and_swap(self, *args, **kwargs):
        return self.inner.compare_and_swap(
            *args,
            **kwargs,
        )

    def delete(self, *args, **kwargs):
        return self.inner.delete(
            *args,
            **kwargs,
        )

    def acquire_lease(self, *args, **kwargs):
        return self.inner.acquire_lease(
            *args,
            **kwargs,
        )

    def renew_lease(self, *args, **kwargs):
        self.renew_count += 1
        if self.renew_count == 2:
            raise LeaseConflict(
                "synthetic second renewal failure"
            )
        return self.inner.renew_lease(
            *args,
            **kwargs,
        )

    def release_lease(self, *args, **kwargs):
        return self.inner.release_lease(
            *args,
            **kwargs,
        )

    def require_fence(self, *args, **kwargs):
        return self.inner.require_fence(
            *args,
            **kwargs,
        )

    def fenced_compare_and_swap(
        self,
        *args,
        **kwargs,
    ):
        return self.inner.fenced_compare_and_swap(
            *args,
            **kwargs,
        )

    def records(self, *args, **kwargs):
        return self.inner.records(
            *args,
            **kwargs,
        )

    def leases(self):
        return self.inner.leases()


def test_partial_multi_resource_renewal_invalidates_and_releases():
    clock = Clock()
    backend = FailSecondRenewBackend(
        clock
    )
    _, _, _, store = environment(
        backend=backend,
        clock=clock,
    )
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
            resource("receipts", root=fp("b")),
        ),
    )
    clock.advance(1.0)
    with pytest.raises(
        DurableMaintenanceStale,
        match="invalidated",
    ):
        store.renew(signed)
    stored = store.get(
        signed.epoch_id
    )
    assert stored is not None
    assert (
        stored.record.state
        is DurableMaintenanceState.INVALIDATED
    )
    assert backend.leases() == ()


class FailSupersedeBackend:
    def __init__(self, clock):
        self.inner = InMemoryFencedStore(
            clock=clock,
        )
        self.fail_supersede = True

    def get(self, *args, **kwargs):
        return self.inner.get(*args, **kwargs)

    def put_if_absent(self, *args, **kwargs):
        return self.inner.put_if_absent(
            *args,
            **kwargs,
        )

    def compare_and_swap(
        self,
        namespace,
        key,
        *,
        expected_revision,
        value,
    ):
        if (
            self.fail_supersede
            and isinstance(
                value,
                DurableMaintenanceRecord,
            )
            and value.state
            is DurableMaintenanceState.SUPERSEDED
        ):
            self.fail_supersede = False
            raise DistributedStateConflict(
                "synthetic parent CAS conflict"
            )
        return self.inner.compare_and_swap(
            namespace,
            key,
            expected_revision=expected_revision,
            value=value,
        )

    def delete(self, *args, **kwargs):
        return self.inner.delete(
            *args,
            **kwargs,
        )

    def acquire_lease(self, *args, **kwargs):
        return self.inner.acquire_lease(
            *args,
            **kwargs,
        )

    def renew_lease(self, *args, **kwargs):
        return self.inner.renew_lease(
            *args,
            **kwargs,
        )

    def release_lease(self, *args, **kwargs):
        return self.inner.release_lease(
            *args,
            **kwargs,
        )

    def require_fence(self, *args, **kwargs):
        return self.inner.require_fence(
            *args,
            **kwargs,
        )

    def fenced_compare_and_swap(
        self,
        *args,
        **kwargs,
    ):
        return self.inner.fenced_compare_and_swap(
            *args,
            **kwargs,
        )

    def records(self, *args, **kwargs):
        return self.inner.records(
            *args,
            **kwargs,
        )

    def leases(self):
        return self.inner.leases()


def test_parent_supersede_cas_failure_invalidates_both_epochs():
    clock = Clock()
    backend = FailSupersedeBackend(
        clock
    )
    _, _, _, store = environment(
        backend=backend,
        clock=clock,
    )
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    clock.advance(1.0)
    with pytest.raises(
        DurableMaintenanceConflict,
        match="commit failed",
    ):
        store.renew(signed)
    parent = store.get(
        signed.epoch_id
    )
    assert parent is not None
    assert parent.record.state is (
        DurableMaintenanceState.INVALIDATED
    )
    assert backend.leases() == ()
    records = backend.records(
        "maintenance"
    )
    active = [
        record
        for record in records
        if isinstance(
            record.value,
            DurableMaintenanceRecord,
        )
        and record.value.state
        is DurableMaintenanceState.ACTIVE
    ]
    assert active == []


def test_partial_acquire_rolls_back_earlier_claims():
    clock, backend, _, store = environment()
    external = backend.acquire_lease(
        store.lease_namespace,
        store._resource_key(
            "receipts"
        ),
        owner="external",
        ttl_seconds=60.0,
    )
    with pytest.raises(
        DurableMaintenanceConflict,
    ):
        acquire(
            store,
            resources=(
                resource(
                    "journal",
                    root=fp("a"),
                ),
                resource(
                    "receipts",
                    root=fp("b"),
                ),
            ),
        )
    # Only the external conflicting claim remains.  The earlier journal
    # acquisition from the failed saga was rolled back.
    leases = backend.leases()
    assert leases == (external,)
    assert not store.active_for_resource(
        "journal"
    )


def test_signature_tamper_invalidates_epoch():
    _, _, _, store = environment()
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    tampered = replace(
        signed,
        signature=replace(
            signed.signature,
            signature="0" * 64,
        ),
    )
    status = store.inspect(tampered)
    assert not status.signature_valid
    assert not status.active
    with pytest.raises(
        DurableMaintenanceStale,
        match="signature",
    ):
        store.require_active(tampered)


def test_missing_persisted_epoch_is_not_active():
    _, backend, _, store = environment()
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    epoch_record = backend.get(
        store.namespace,
        store._epoch_key(
            signed.epoch_id
        ),
    )
    backend.delete(
        store.namespace,
        store._epoch_key(
            signed.epoch_id
        ),
        expected_revision=(
            epoch_record.revision
        ),
    )
    with pytest.raises(
        DurableMaintenanceConflict,
        match="partially missing",
    ):
        store.inspect(signed)


def test_missing_persisted_record_is_detected():
    _, backend, _, store = environment()
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    record = backend.get(
        store.namespace,
        store._record_key(
            signed.epoch_id
        ),
    )
    backend.delete(
        store.namespace,
        store._record_key(
            signed.epoch_id
        ),
        expected_revision=record.revision,
    )
    with pytest.raises(
        DurableMaintenanceConflict,
        match="partially missing",
    ):
        store.get(signed.epoch_id)


def test_get_unknown_epoch_returns_none():
    _, _, _, store = environment()
    assert store.get(fp("f")) is None


def test_active_for_resource_reports_busy_and_free_without_leaking_probe():
    _, backend, _, store = environment()
    assert not store.active_for_resource(
        "journal"
    )
    assert backend.leases() == ()
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    assert store.active_for_resource(
        "journal"
    )
    assert len(backend.leases()) == 1
    store.release(signed)
    assert not store.active_for_resource(
        "journal"
    )
    assert backend.leases() == ()


def test_assert_available_releases_probe_leases():
    _, backend, _, store = environment()
    store.assert_available(
        ("journal", "receipts")
    )
    assert backend.leases() == ()


def test_assert_available_rejects_reserved_resource():
    _, _, _, store = environment()
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    with pytest.raises(
        DurableMaintenanceConflict,
        match="reserved",
    ):
        store.assert_available(
            ("journal",)
        )
    assert store.require_active(
        signed
    ).active


def test_guard_delegates_operation_and_resource_checks():
    _, _, _, store = environment()
    signed = acquire(
        store,
        operation=(
            DurableMaintenanceOperation.FAILOVER
        ),
        resources=(
            resource("source", root=fp("a")),
            resource("target", root=fp("b")),
        ),
    )
    guard = DurableMaintenanceGuard(
        store,
        signed,
    )
    status = guard.require(
        operation=(
            DurableMaintenanceOperation.FAILOVER
        ),
        resources=("source", "target"),
    )
    assert status.active
    data = guard.to_dict()
    assert data["epoch_id"] == signed.epoch_id
    assert data["operation"] == "failover"
    assert data["resources"] == [
        "source",
        "target",
    ]


def test_guard_rejects_wrong_types():
    _, _, _, store = environment()
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    with pytest.raises(TypeError, match="store"):
        DurableMaintenanceGuard(
            object(),
            signed,
        )
    with pytest.raises(TypeError, match="signed"):
        DurableMaintenanceGuard(
            store,
            object(),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_resources": 0},
        {"max_resources": True},
        {"default_ttl_seconds": 0.0},
        {"max_ttl_seconds": 0.0},
        {"max_renewals": 0},
        {"max_renewals": True},
        {"require_state_commitments": "yes"},
    ],
)
def test_policy_validation(kwargs):
    with pytest.raises(ValueError):
        DurableMaintenancePolicy(**kwargs)


def test_policy_default_ttl_may_not_exceed_max():
    with pytest.raises(
        ValueError,
        match="exceeds",
    ):
        DurableMaintenancePolicy(
            default_ttl_seconds=20.0,
            max_ttl_seconds=10.0,
        )


def test_policy_digest_is_stable():
    first = DurableMaintenancePolicy()
    second = DurableMaintenancePolicy()
    assert first.digest == second.digest
    assert len(first.digest) == 64


def test_policy_can_allow_missing_state_commitment():
    policy = DurableMaintenancePolicy(
        require_state_commitments=False,
    )
    _, _, _, store = environment(
        policy=policy,
    )
    signed = acquire(
        store,
        resources=(
            DurableMaintenanceResource(
                "journal",
                "chain",
                10,
                fp("a"),
                "",
            ),
        ),
    )
    assert store.require_active(signed).active


def test_default_policy_requires_state_commitment():
    _, _, _, store = environment()
    with pytest.raises(
        ValueError,
        match="state_digest",
    ):
        acquire(
            store,
            resources=(
                DurableMaintenanceResource(
                    "journal",
                    "chain",
                    10,
                    fp("a"),
                    "",
                ),
            ),
        )


def test_resource_validation():
    with pytest.raises(ValueError):
        DurableMaintenanceResource(
            "",
            "chain",
            1,
            fp("a"),
            fp("b"),
        )
    with pytest.raises(ValueError):
        DurableMaintenanceResource(
            "journal",
            "",
            1,
            fp("a"),
            fp("b"),
        )
    with pytest.raises(ValueError):
        DurableMaintenanceResource(
            "journal",
            "chain",
            -1,
            fp("a"),
            fp("b"),
        )
    with pytest.raises(ValueError):
        DurableMaintenanceResource(
            "journal",
            "chain",
            1,
            "bad",
            fp("b"),
        )
    with pytest.raises(ValueError):
        DurableMaintenanceResource(
            "journal",
            "chain",
            0,
            fp("a"),
            fp("b"),
        )


def test_genesis_resource_is_valid():
    value = resource(
        "journal",
        sequence=0,
    )
    assert value.sequence == 0
    assert value.root_hash == GENESIS_ROOT


def test_resource_digest_changes_with_state():
    first = resource(
        "journal",
        root=fp("a"),
        state=fp("b"),
    )
    second = replace(
        first,
        state_digest=fp("c"),
    )
    assert first.digest != second.digest


def test_claim_round_trip_to_fenced_lease():
    lease = FencedLease(
        "leases",
        "key",
        "owner",
        7,
        10.0,
        20.0,
    )
    claim = DurableMaintenanceClaim.from_lease(
        "journal",
        lease,
    )
    assert claim.lease() == lease
    assert claim.fencing_token == 7


def test_claim_validation():
    with pytest.raises(ValueError):
        DurableMaintenanceClaim(
            "",
            "leases",
            "key",
            "owner",
            1,
            1.0,
            2.0,
        )
    with pytest.raises(ValueError):
        DurableMaintenanceClaim(
            "journal",
            "leases",
            "key",
            "owner",
            0,
            1.0,
            2.0,
        )
    with pytest.raises(ValueError):
        DurableMaintenanceClaim(
            "journal",
            "leases",
            "key",
            "owner",
            1,
            2.0,
            1.0,
        )


def test_epoch_resource_claim_order_validation():
    res_a = resource(
        "a",
        root=fp("a"),
    )
    res_b = resource(
        "b",
        root=fp("b"),
    )
    claim_a = DurableMaintenanceClaim(
        "a",
        "leases",
        "a",
        "owner",
        1,
        1.0,
        2.0,
    )
    claim_b = DurableMaintenanceClaim(
        "b",
        "leases",
        "b",
        "owner",
        2,
        1.0,
        2.0,
    )
    epoch_id = DurableMaintenanceEpoch.derive_id(
        operation=(
            DurableMaintenanceOperation.COMPACTION
        ),
        owner_id="operator",
        lease_owner="owner",
        generation=2,
        renewal_count=0,
        resources=(res_a, res_b),
        claims=(claim_a, claim_b),
        policy_digest=fp("p"),
        nonce="nonce",
        issued_at=1.0,
        expires_at=2.0,
    )
    valid = DurableMaintenanceEpoch(
        1,
        epoch_id,
        DurableMaintenanceOperation.COMPACTION,
        "operator",
        "owner",
        2,
        0,
        (res_a, res_b),
        (claim_a, claim_b),
        fp("p"),
        "nonce",
        1.0,
        2.0,
    )
    assert valid.resource_ids == ("a", "b")

    with pytest.raises(ValueError, match="sorted"):
        replace(
            valid,
            resources=(res_b, res_a),
            claims=(claim_b, claim_a),
        )
    with pytest.raises(ValueError, match="align"):
        replace(
            valid,
            claims=(claim_b, claim_a),
        )


def test_initial_epoch_may_not_have_parent():
    _, _, _, store = environment()
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    with pytest.raises(
        ValueError,
        match="initial",
    ):
        replace(
            signed.epoch,
            parent_epoch_id=fp("p"),
        )


def test_renewed_epoch_requires_parent():
    _, _, _, store = environment()
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    with pytest.raises(
        ValueError,
        match="requires parent",
    ):
        replace(
            signed.epoch,
            renewal_count=1,
            parent_epoch_id="",
        )


def test_signed_epoch_rejects_wrong_artifact_type():
    _, _, _, store = environment()
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    bad = replace(
        signed.signature,
        artifact_type="wrong",
    )
    with pytest.raises(
        ValueError,
        match="artifact type",
    ):
        SignedDurableMaintenanceEpoch(
            signed.epoch,
            bad,
        )


def test_signed_epoch_rejects_digest_mismatch():
    _, _, _, store = environment()
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    bad = replace(
        signed.signature,
        artifact_digest=fp("f"),
    )
    with pytest.raises(
        ValueError,
        match="digest mismatch",
    ):
        SignedDurableMaintenanceEpoch(
            signed.epoch,
            bad,
        )


def test_record_validation_for_released_and_superseded():
    with pytest.raises(
        ValueError,
        match="released_at",
    ):
        DurableMaintenanceRecord(
            fp("a"),
            fp("b"),
            DurableMaintenanceOperation.PRUNING,
            "owner",
            1,
            DurableMaintenanceState.RELEASED,
            1.0,
            2.0,
        )
    with pytest.raises(
        ValueError,
        match="replacement",
    ):
        DurableMaintenanceRecord(
            fp("a"),
            fp("b"),
            DurableMaintenanceOperation.PRUNING,
            "owner",
            1,
            DurableMaintenanceState.SUPERSEDED,
            1.0,
            2.0,
        )


def test_max_resource_limit():
    policy = DurableMaintenancePolicy(
        max_resources=2,
    )
    _, _, _, store = environment(
        policy=policy,
    )
    with pytest.raises(
        ValueError,
        match="resource count",
    ):
        acquire(
            store,
            resources=(
                resource("a", root=fp("a")),
                resource("b", root=fp("b")),
                resource("c", root=fp("c")),
            ),
        )


def test_duplicate_resource_ids_rejected():
    _, _, _, store = environment()
    with pytest.raises(
        ValueError,
        match="unique",
    ):
        acquire(
            store,
            resources=(
                resource("same", root=fp("a")),
                resource("same", root=fp("a")),
            ),
        )


@pytest.mark.parametrize(
    "ttl",
    [0.0, -1.0, float("nan"), float("inf"), True],
)
def test_ttl_validation(ttl):
    _, _, _, store = environment()
    with pytest.raises(
        ValueError,
        match="TTL",
    ):
        acquire(
            store,
            resources=(
                resource("journal", root=fp("a")),
            ),
            ttl=ttl,
        )


def test_ttl_maximum_enforced():
    policy = DurableMaintenancePolicy(
        max_ttl_seconds=10.0,
        default_ttl_seconds=5.0,
    )
    _, _, _, store = environment(
        policy=policy,
    )
    with pytest.raises(
        ValueError,
        match="TTL",
    ):
        acquire(
            store,
            resources=(
                resource("journal", root=fp("a")),
            ),
            ttl=11.0,
        )


def test_invalid_nonce_factory_fails_before_authority_persists():
    clock = Clock()
    backend = InMemoryFencedStore(
        clock=clock,
    )
    signer = ArtifactSigner(
        "maintenance",
        b"k" * 32,
        clock=clock,
    )
    store = DurableMaintenanceStore(
        backend,
        signer,
        namespace="maintenance",
        clock=clock,
        nonce_factory=lambda: "",
    )
    with pytest.raises(ValueError, match="nonce"):
        acquire(
            store,
            resources=(
                resource("journal", root=fp("a")),
            ),
        )
    assert backend.leases() == ()


def test_status_to_dict_exposes_authority_decision():
    _, _, _, store = environment()
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    data = store.require_active(
        signed
    ).to_dict()
    assert data["active"] is True
    assert (
        data["destructive_action_authorized"]
        is True
    )
    assert data["reasons"] == []
    assert (
        data["epoch"]["epoch"]["epoch_id"]
        == signed.epoch_id
    )


def test_signed_epoch_to_dict_round_trip_shape():
    _, _, _, store = environment()
    signed = acquire(
        store,
        resources=(
            resource("journal", root=fp("a")),
        ),
    )
    data = signed.to_dict()
    assert data["epoch"]["epoch_id"] == (
        signed.epoch_id
    )
    assert (
        data["signature"]["artifact_type"]
        == MAINTENANCE_ARTIFACT_TYPE
    )


def test_store_constructor_validation():
    clock = Clock()
    backend = InMemoryFencedStore(
        clock=clock,
    )
    signer = ArtifactSigner(
        "maintenance",
        b"k" * 32,
        clock=clock,
    )
    with pytest.raises(TypeError, match="backend"):
        DurableMaintenanceStore(
            object(),
            signer,
        )
    with pytest.raises(TypeError, match="signer"):
        DurableMaintenanceStore(
            backend,
            object(),
        )
    with pytest.raises(ValueError, match="namespace"):
        DurableMaintenanceStore(
            backend,
            signer,
            namespace="",
        )
    with pytest.raises(ValueError, match="max_cas_retries"):
        DurableMaintenanceStore(
            backend,
            signer,
            max_cas_retries=0,
        )
    with pytest.raises(TypeError, match="clock"):
        DurableMaintenanceStore(
            backend,
            signer,
            clock=object(),
        )
    with pytest.raises(TypeError, match="nonce_factory"):
        DurableMaintenanceStore(
            backend,
            signer,
            nonce_factory=object(),
        )


def test_get_rejects_wrong_epoch_value_type():
    _, backend, _, store = environment()
    epoch_id = fp("a")
    backend.put_if_absent(
        store.namespace,
        store._epoch_key(epoch_id),
        {"bad": True},
    )
    backend.put_if_absent(
        store.namespace,
        store._record_key(epoch_id),
        DurableMaintenanceRecord(
            epoch_id,
            fp("b"),
            DurableMaintenanceOperation.PRUNING,
            "owner",
            1,
            DurableMaintenanceState.ACTIVE,
            1.0,
            1.0,
        ),
    )
    with pytest.raises(
        DurableMaintenanceConflict,
        match="epoch value",
    ):
        store.get(epoch_id)


def test_get_rejects_wrong_record_value_type():
    _, backend, _, store = environment()
    epoch_id = fp("a")
    signature = SignedArtifact(
        MAINTENANCE_ARTIFACT_TYPE,
        fp("b"),
        "maintenance",
        1.0,
        {},
        fp("c"),
    )
    # A partial/corrupt pair is enough to exercise record type validation.
    backend.put_if_absent(
        store.namespace,
        store._epoch_key(epoch_id),
        signature,
    )
    backend.put_if_absent(
        store.namespace,
        store._record_key(epoch_id),
        {"bad": True},
    )
    with pytest.raises(
        DurableMaintenanceConflict,
    ):
        store.get(epoch_id)

class ResourceHead:
    def __init__(self, sequence, root_hash):
        self.sequence = sequence
        self.root_hash = root_hash


class ResourceChain:
    def __init__(self, sequence=7, root_hash=None):
        self._head = ResourceHead(
            sequence,
            root_hash or fp("r"),
        )

    def head(self):
        return self._head


def test_maintenance_resource_from_chain_builds_live_commitment():
    chain = ResourceChain(
        sequence=7,
        root_hash=fp("r"),
    )
    item = DurableMaintenanceResource.from_chain(
        "journal",
        chain,
    )
    assert item.resource_id == "journal"
    assert item.resource_kind == "evidence-chain"
    assert item.sequence == 7
    assert item.root_hash == fp("r")
    assert len(item.state_digest) == 64


def test_maintenance_resource_from_chain_digest_changes_with_head():
    first = DurableMaintenanceResource.from_chain(
        "journal",
        ResourceChain(
            sequence=7,
            root_hash=fp("a"),
        ),
    )
    second = DurableMaintenanceResource.from_chain(
        "journal",
        ResourceChain(
            sequence=8,
            root_hash=fp("b"),
        ),
    )
    assert first.state_digest != second.state_digest
    assert first != second


def test_maintenance_resource_from_chain_custom_kind():
    item = DurableMaintenanceResource.from_chain(
        "journal",
        ResourceChain(),
        resource_kind="orphan-gc-chain",
    )
    assert item.resource_kind == "orphan-gc-chain"


def test_maintenance_resource_from_chain_requires_head():
    with pytest.raises(
        TypeError,
        match="head",
    ):
        DurableMaintenanceResource.from_chain(
            "journal",
            object(),
        )


def test_maintenance_resource_from_chain_requires_head_shape():
    class Bad:
        def head(self):
            return object()

    with pytest.raises(
        TypeError,
        match="sequence and root_hash",
    ):
        DurableMaintenanceResource.from_chain(
            "journal",
            Bad(),
        )


@pytest.mark.parametrize(
    "chain_id",
    ["", "x" * 257],
)
def test_maintenance_resource_from_chain_validates_chain_id(chain_id):
    with pytest.raises(ValueError, match="chain_id"):
        DurableMaintenanceResource.from_chain(
            chain_id,
            ResourceChain(),
        )


def test_maintenance_resource_replicated_chain_binds_both_sides():
    item = DurableMaintenanceResource.replicated_chain(
        "journal",
        source_sequence=10,
        source_root=fp("a"),
        target_sequence=8,
        target_root=fp("b"),
        replication_state_digest=fp("c"),
    )
    assert item.resource_id == "journal"
    assert item.resource_kind == "replicated-evidence-chain"
    assert item.sequence == 10
    assert item.state_digest == fp("c")
    assert item.root_hash not in {
        fp("a"),
        fp("b"),
    }


def test_maintenance_resource_replicated_chain_derives_state_when_missing():
    item = DurableMaintenanceResource.replicated_chain(
        "journal",
        source_sequence=2,
        source_root=fp("a"),
        target_sequence=2,
        target_root=fp("b"),
    )
    assert len(item.state_digest) == 64
    assert item.state_digest == item.root_hash


@pytest.mark.parametrize(
    "name,value",
    [
        ("source_sequence", -1),
        ("source_sequence", True),
        ("target_sequence", -1),
        ("target_sequence", True),
    ],
)
def test_maintenance_resource_replicated_chain_validates_sequences(name, value):
    kwargs = dict(
        chain_id="journal",
        source_sequence=1,
        source_root=fp("a"),
        target_sequence=1,
        target_root=fp("b"),
    )
    kwargs[name] = value
    with pytest.raises(ValueError):
        DurableMaintenanceResource.replicated_chain(
            **kwargs
        )


def test_maintenance_resource_replica_binds_journal_and_receipts():
    item = DurableMaintenanceResource.replica(
        "replica-a",
        journal_sequence=20,
        journal_root=fp("j"),
        receipt_sequence=18,
        receipt_root=fp("r"),
        replication_state_digest=fp("s"),
    )
    assert item.resource_id == "replica-a"
    assert item.resource_kind == "evidence-replica"
    assert item.sequence == 20
    assert item.state_digest == fp("s")
    assert len(item.root_hash) == 64


def test_maintenance_resource_replica_derived_state_changes_with_receipt_root():
    first = DurableMaintenanceResource.replica(
        "replica-a",
        journal_sequence=20,
        journal_root=fp("j"),
        receipt_sequence=18,
        receipt_root=fp("r"),
    )
    second = DurableMaintenanceResource.replica(
        "replica-a",
        journal_sequence=20,
        journal_root=fp("j"),
        receipt_sequence=18,
        receipt_root=fp("x"),
    )
    assert first.state_digest != second.state_digest
    assert first.root_hash != second.root_hash


def test_orphan_gc_is_first_class_maintenance_operation():
    _, _, _, store = environment()
    item = resource(
        "journal",
        kind="orphan-gc-chain",
        root=fp("j"),
    )
    signed = acquire(
        store,
        operation=DurableMaintenanceOperation.ORPHAN_GC,
        resources=(item,),
    )
    status = store.require_active(
        signed,
        operation=DurableMaintenanceOperation.ORPHAN_GC,
        required_resources=("journal",),
        live_resources=(item,),
    )
    assert status.active
    assert status.destructive_action_authorized
    assert signed.epoch.operation.value == "orphan_gc"


def test_orphan_gc_epoch_rejects_other_operation_check():
    _, _, _, store = environment()
    item = resource(
        "journal",
        kind="orphan-gc-chain",
        root=fp("j"),
    )
    signed = acquire(
        store,
        operation=DurableMaintenanceOperation.ORPHAN_GC,
        resources=(item,),
    )
    with pytest.raises(
        DurableMaintenanceStale,
        match="operation",
    ):
        store.require_active(
            signed,
            operation=DurableMaintenanceOperation.PRUNING,
            required_resources=("journal",),
            live_resources=(item,),
        )


def test_resource_helpers_are_not_policy_methods():
    assert not hasattr(
        DurableMaintenancePolicy,
        "from_chain",
    )
    assert not hasattr(
        DurableMaintenancePolicy,
        "replicated_chain",
    )
    assert not hasattr(
        DurableMaintenancePolicy,
        "replica",
    )
    assert hasattr(
        DurableMaintenanceResource,
        "from_chain",
    )
    assert hasattr(
        DurableMaintenanceResource,
        "replicated_chain",
    )
    assert hasattr(
        DurableMaintenanceResource,
        "replica",
    )

