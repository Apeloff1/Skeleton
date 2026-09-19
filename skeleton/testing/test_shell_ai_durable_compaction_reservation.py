"""Signed exclusive durable compaction reservation tests."""

from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

from skeleton.shells.ai.distributed_state import (
    DistributedStateConflict,
    InMemoryFencedStore,
)
from skeleton.shells.ai.durable_compaction_reservation import (
    DurableCompactionReservation,
    DurableCompactionReservationConflict,
    DurableCompactionReservationError,
    DurableCompactionReservationHead,
    DurableCompactionReservationStatus,
    DurableCompactionReservationStore,
    SignedDurableCompactionReservation,
)
from skeleton.shells.ai.signed_artifact import (
    ArtifactSigner,
    SignedArtifact,
)


def fp(value: str) -> str:
    return hashlib.sha256(
        value.encode()
    ).hexdigest()


class Fixture:
    def __init__(
        self,
        *,
        backend=None,
        now=100.0,
        ttl=60.0,
    ):
        self.backend = (
            backend
            or InMemoryFencedStore()
        )
        self.now = [float(now)]
        self.nonce = [0]

        def nonce():
            self.nonce[0] += 1
            return f"nonce-{self.nonce[0]}"

        self.signer = ArtifactSigner(
            "reservation",
            b"r" * 32,
            clock=lambda: self.now[0],
        )
        self.store = (
            DurableCompactionReservationStore(
                self.backend,
                self.signer,
                namespace="reservations",
                ttl_seconds=ttl,
                max_ttl_seconds=3600.0,
                clock=lambda: self.now[0],
                nonce_factory=nonce,
            )
        )

    def acquire(
        self,
        chain="journal",
        *,
        holder="group-a",
        operator="operator",
        **kwargs,
    ):
        return self.store.acquire(
            chain,
            holder_id=holder,
            operator_id=operator,
            **kwargs,
        )


def test_acquire_creates_signed_active_reservation():
    fixture = Fixture()
    item = fixture.acquire()
    reservation = item.reservation

    assert reservation.chain_id == "journal"
    assert reservation.holder_id == "group-a"
    assert reservation.operator_id == "operator"
    assert reservation.generation == 1
    assert reservation.issued_at == 100.0
    assert reservation.expires_at == 160.0
    assert len(reservation.reservation_id) == 64
    assert len(reservation.digest) == 64
    assert not item.destructive_action_authorized
    assert (
        item.signature.artifact_type
        == "durable-compaction-reservation"
    )
    assert (
        item.signature.artifact_digest
        == reservation.digest
    )
    assert (
        item.signature.metadata["authority"]
        == "durable-compaction-reservation"
    )
    assert fixture.store.current(
        "journal"
    ) == item


def test_same_holder_acquire_reuses_active_reservation():
    fixture = Fixture()
    first = fixture.acquire()
    fixture.now[0] = 120.0
    second = fixture.acquire()
    assert second == first
    assert (
        second.reservation.generation
        == 1
    )
    assert fixture.nonce[0] == 1


def test_other_holder_is_rejected_while_active():
    fixture = Fixture()
    fixture.acquire()
    with pytest.raises(
        DurableCompactionReservationConflict,
        match="another",
    ):
        fixture.acquire(
            holder="group-b",
        )


def test_other_operator_is_rejected_while_active():
    fixture = Fixture()
    fixture.acquire()
    with pytest.raises(
        DurableCompactionReservationConflict,
    ):
        fixture.acquire(
            operator="other",
        )


def test_expired_reservation_is_not_current():
    fixture = Fixture(ttl=10.0)
    first = fixture.acquire()
    fixture.now[0] = (
        first.reservation.expires_at
    )
    assert (
        fixture.store.current(
            "journal"
        )
        is None
    )
    status = fixture.store.status(
        "journal"
    )
    assert not status.active
    assert status.expired
    assert not status.released


def test_expiry_allows_new_holder_with_higher_generation():
    fixture = Fixture(ttl=10.0)
    first = fixture.acquire()
    fixture.now[0] = 111.0
    second = fixture.acquire(
        holder="group-b",
        operator="operator-b",
    )
    assert (
        second.reservation.generation
        == first.reservation.generation + 1
    )
    assert (
        second.reservation.holder_id
        == "group-b"
    )
    assert (
        fixture.store.current(
            "journal"
        )
        == second
    )


def test_renew_increments_generation_and_expiry():
    fixture = Fixture(ttl=30.0)
    first = fixture.acquire()
    fixture.now[0] = 110.0
    second = fixture.store.renew(
        "journal",
        holder_id="group-a",
        operator_id="operator",
    )
    assert (
        second.reservation.generation
        == 2
    )
    assert second.reservation.issued_at == 110.0
    assert second.reservation.expires_at == 140.0
    assert (
        second.reservation_id
        != first.reservation_id
    )


def test_renew_other_holder_is_rejected():
    fixture = Fixture()
    fixture.acquire()
    with pytest.raises(
        DurableCompactionReservationConflict,
        match="another",
    ):
        fixture.store.renew(
            "journal",
            holder_id="group-b",
            operator_id="operator",
        )


def test_force_renew_same_holder_changes_reservation():
    fixture = Fixture()
    first = fixture.acquire()
    second = fixture.acquire(
        force_renew=True,
    )
    assert (
        second.reservation.generation
        == first.reservation.generation + 1
    )
    assert second != first


def test_require_holder_accepts_exact_holder_and_operator():
    fixture = Fixture()
    item = fixture.acquire()
    assert (
        fixture.store.require_holder(
            "journal",
            holder_id="group-a",
            operator_id="operator",
        )
        == item
    )


def test_require_holder_rejects_missing_reservation():
    fixture = Fixture()
    with pytest.raises(
        DurableCompactionReservationConflict,
        match="no active",
    ):
        fixture.store.require_holder(
            "journal",
            holder_id="group-a",
        )


def test_require_holder_rejects_wrong_holder():
    fixture = Fixture()
    fixture.acquire()
    with pytest.raises(
        DurableCompactionReservationConflict,
        match="different holder",
    ):
        fixture.store.require_holder(
            "journal",
            holder_id="group-b",
        )


def test_require_holder_rejects_wrong_operator():
    fixture = Fixture()
    fixture.acquire()
    with pytest.raises(
        DurableCompactionReservationConflict,
        match="operator",
    ):
        fixture.store.require_holder(
            "journal",
            holder_id="group-a",
            operator_id="other",
        )


def test_assert_available_allows_unreserved_chain():
    fixture = Fixture()
    fixture.store.assert_available(
        "journal"
    )


def test_assert_available_rejects_foreign_active_reservation():
    fixture = Fixture()
    fixture.acquire()
    with pytest.raises(
        DurableCompactionReservationConflict,
    ):
        fixture.store.assert_available(
            "journal"
        )


def test_assert_available_allows_matching_holder():
    fixture = Fixture()
    fixture.acquire()
    fixture.store.assert_available(
        "journal",
        holder_id="group-a",
    )


def test_release_marks_head_released_and_current_empty():
    fixture = Fixture()
    item = fixture.acquire()
    head = fixture.store.release(
        "journal",
        holder_id="group-a",
    )
    assert head.released
    assert head.released_at == 100.0
    assert (
        head.reservation_id
        == item.reservation_id
    )
    assert (
        fixture.store.current(
            "journal"
        )
        is None
    )
    status = fixture.store.status(
        "journal"
    )
    assert not status.active
    assert status.released
    assert not status.expired


def test_release_retry_is_idempotent():
    fixture = Fixture()
    fixture.acquire()
    first = fixture.store.release(
        "journal",
        holder_id="group-a",
    )
    second = fixture.store.release(
        "journal",
        holder_id="group-a",
    )
    assert second == first


def test_release_wrong_holder_is_rejected():
    fixture = Fixture()
    fixture.acquire()
    with pytest.raises(
        DurableCompactionReservationConflict,
        match="another",
    ):
        fixture.store.release(
            "journal",
            holder_id="group-b",
        )


def test_release_missing_chain_is_rejected():
    fixture = Fixture()
    with pytest.raises(
        DurableCompactionReservationConflict,
        match="no reservation",
    ):
        fixture.store.release(
            "journal",
            holder_id="group-a",
        )


def test_released_chain_can_be_acquired_by_new_holder():
    fixture = Fixture()
    first = fixture.acquire()
    fixture.store.release(
        "journal",
        holder_id="group-a",
    )
    second = fixture.acquire(
        holder="group-b",
        operator="operator-b",
    )
    assert (
        second.reservation.generation
        == first.reservation.generation + 1
    )


def test_status_missing_chain_is_empty():
    fixture = Fixture()
    status = fixture.store.status(
        "journal"
    )
    assert status == (
        DurableCompactionReservationStatus(
            "journal",
            False,
            False,
            False,
            "",
            "",
            "",
            0,
            0.0,
        )
    )


def test_status_active_chain_exposes_owner():
    fixture = Fixture()
    item = fixture.acquire()
    status = fixture.store.status(
        "journal"
    )
    assert status.active
    assert not status.expired
    assert not status.released
    assert status.holder_id == "group-a"
    assert status.operator_id == "operator"
    assert (
        status.reservation_id
        == item.reservation_id
    )
    assert status.generation == 1
    assert status.expires_at == 160.0


def test_fresh_reader_verifies_active_reservation():
    fixture = Fixture()
    item = fixture.acquire()
    fresh = (
        DurableCompactionReservationStore(
            fixture.backend,
            ArtifactSigner(
                "reservation",
                b"r" * 32,
                clock=lambda: fixture.now[0],
            ),
            namespace="reservations",
            clock=lambda: fixture.now[0],
        )
    )
    assert fresh.get(
        item.reservation_id
    ) == item
    assert fresh.current(
        "journal"
    ) == item


def test_wrong_signer_cannot_verify_reservation():
    fixture = Fixture()
    item = fixture.acquire()
    wrong = (
        DurableCompactionReservationStore(
            fixture.backend,
            ArtifactSigner(
                "wrong",
                b"w" * 32,
            ),
            namespace="reservations",
        )
    )
    with pytest.raises(
        DurableCompactionReservationError,
        match="signature",
    ):
        wrong.get(
            item.reservation_id
        )


def test_signature_tamper_is_rejected():
    fixture = Fixture()
    item = fixture.acquire()
    key = fixture.store._item_key(
        item.reservation_id
    )
    record = fixture.backend.get(
        fixture.store.namespace,
        key,
    )
    tampered_signature = replace(
        item.signature,
        signature="f" * 64,
    )
    tampered = replace(
        item,
        signature=tampered_signature,
    )
    fixture.backend.compare_and_swap(
        fixture.store.namespace,
        key,
        expected_revision=record.revision,
        value=tampered,
    )
    with pytest.raises(
        DurableCompactionReservationError,
        match="signature verification",
    ):
        fixture.store.get(
            item.reservation_id
        )


def test_signature_metadata_tamper_is_rejected():
    fixture = Fixture()
    item = fixture.acquire()
    key = fixture.store._item_key(
        item.reservation_id
    )
    record = fixture.backend.get(
        fixture.store.namespace,
        key,
    )
    metadata = dict(
        item.signature.metadata
    )
    metadata["holder_id"] = (
        "group-b"
    )
    tampered = replace(
        item,
        signature=replace(
            item.signature,
            metadata=metadata,
        ),
    )
    fixture.backend.compare_and_swap(
        fixture.store.namespace,
        key,
        expected_revision=record.revision,
        value=tampered,
    )
    with pytest.raises(
        DurableCompactionReservationError,
        match="metadata",
    ):
        fixture.store.get(
            item.reservation_id
        )


def test_signature_artifact_type_tamper_is_rejected():
    fixture = Fixture()
    item = fixture.acquire()
    key = fixture.store._item_key(
        item.reservation_id
    )
    record = fixture.backend.get(
        fixture.store.namespace,
        key,
    )
    tampered = replace(
        item,
        signature=replace(
            item.signature,
            artifact_type="wrong-type",
        ),
    )
    fixture.backend.compare_and_swap(
        fixture.store.namespace,
        key,
        expected_revision=record.revision,
        value=tampered,
    )
    with pytest.raises(
        DurableCompactionReservationError,
        match="artifact type",
    ):
        fixture.store.get(
            item.reservation_id
        )


def test_reservation_payload_tamper_is_rejected():
    fixture = Fixture()
    item = fixture.acquire()
    key = fixture.store._item_key(
        item.reservation_id
    )
    record = fixture.backend.get(
        fixture.store.namespace,
        key,
    )
    tampered = replace(
        item,
        reservation=replace(
            item.reservation,
            operator_id="different",
        ),
    )
    fixture.backend.compare_and_swap(
        fixture.store.namespace,
        key,
        expected_revision=record.revision,
        value=tampered,
    )
    with pytest.raises(
        DurableCompactionReservationError,
        match="digest",
    ):
        fixture.store.get(
            item.reservation_id
        )


def test_head_missing_item_is_corruption():
    fixture = Fixture()
    fixture.backend.put_if_absent(
        fixture.store.namespace,
        fixture.store._head_key(
            "journal"
        ),
        DurableCompactionReservationHead(
            "journal",
            fp("missing"),
            1,
            0.0,
        ),
    )
    with pytest.raises(
        DurableCompactionReservationError,
        match="missing item",
    ):
        fixture.store.current(
            "journal"
        )


def test_head_wrong_value_type_is_rejected():
    fixture = Fixture()
    fixture.backend.put_if_absent(
        fixture.store.namespace,
        fixture.store._head_key(
            "journal"
        ),
        {"bad": True},
    )
    with pytest.raises(
        DurableCompactionReservationError,
        match="head",
    ):
        fixture.store.current(
            "journal"
        )


def test_head_chain_identity_tamper_is_rejected():
    fixture = Fixture()
    item = fixture.acquire()
    head_key = fixture.store._head_key(
        "journal"
    )
    record = fixture.backend.get(
        fixture.store.namespace,
        head_key,
    )
    fixture.backend.compare_and_swap(
        fixture.store.namespace,
        head_key,
        expected_revision=record.revision,
        value=DurableCompactionReservationHead(
            "other",
            item.reservation_id,
            1,
            0.0,
        ),
    )
    with pytest.raises(
        DurableCompactionReservationError,
        match="chain mismatch",
    ):
        fixture.store.current(
            "journal"
        )


def test_head_generation_tamper_is_rejected():
    fixture = Fixture()
    item = fixture.acquire()
    head_key = fixture.store._head_key(
        "journal"
    )
    record = fixture.backend.get(
        fixture.store.namespace,
        head_key,
    )
    fixture.backend.compare_and_swap(
        fixture.store.namespace,
        head_key,
        expected_revision=record.revision,
        value=DurableCompactionReservationHead(
            "journal",
            item.reservation_id,
            2,
            0.0,
        ),
    )
    with pytest.raises(
        DurableCompactionReservationError,
        match="binding mismatch",
    ):
        fixture.store.current(
            "journal"
        )


def test_acquire_many_holds_sorted_unique_chains():
    fixture = Fixture()
    items = fixture.store.acquire_many(
        ("receipts", "journal"),
        holder_id="group-a",
        operator_id="operator",
    )
    assert [
        item.chain_id
        for item in items
    ] == [
        "journal",
        "receipts",
    ]
    assert all(
        item.holder_id == "group-a"
        for item in items
    )


def test_acquire_many_reuses_existing_same_holder():
    fixture = Fixture()
    journal = fixture.acquire(
        "journal"
    )
    items = fixture.store.acquire_many(
        ("journal", "receipts"),
        holder_id="group-a",
        operator_id="operator",
    )
    assert items[0] == journal
    assert (
        fixture.store.current(
            "journal"
        )
        == journal
    )


def test_acquire_many_preflight_conflict_does_not_take_free_chain():
    fixture = Fixture()
    fixture.acquire(
        "receipts",
        holder="group-b",
        operator="operator-b",
    )
    with pytest.raises(
        DurableCompactionReservationConflict,
        match="another owner",
    ):
        fixture.store.acquire_many(
            ("journal", "receipts"),
            holder_id="group-a",
            operator_id="operator",
        )
    assert (
        fixture.store.current(
            "journal"
        )
        is None
    )
    assert (
        fixture.store.current(
            "receipts"
        ).holder_id
        == "group-b"
    )


def test_acquire_many_failure_does_not_release_prior_same_holder():
    fixture = Fixture()
    existing = fixture.acquire(
        "journal"
    )
    fixture.acquire(
        "receipts",
        holder="group-b",
        operator="operator-b",
    )
    with pytest.raises(
        DurableCompactionReservationConflict,
    ):
        fixture.store.acquire_many(
            ("journal", "receipts"),
            holder_id="group-a",
            operator_id="operator",
        )
    assert (
        fixture.store.current(
            "journal"
        )
        == existing
    )


def test_renew_many_increments_all_generations():
    fixture = Fixture()
    first = fixture.store.acquire_many(
        ("journal", "receipts"),
        holder_id="group-a",
        operator_id="operator",
    )
    fixture.now[0] = 120.0
    second = fixture.store.acquire_many(
        ("journal", "receipts"),
        holder_id="group-a",
        operator_id="operator",
        renew=True,
    )
    assert [
        item.reservation.generation
        for item in first
    ] == [1, 1]
    assert [
        item.reservation.generation
        for item in second
    ] == [2, 2]


def test_release_many_releases_every_chain():
    fixture = Fixture()
    fixture.store.acquire_many(
        ("journal", "receipts"),
        holder_id="group-a",
        operator_id="operator",
    )
    heads = fixture.store.release_many(
        ("receipts", "journal"),
        holder_id="group-a",
    )
    assert len(heads) == 2
    assert all(
        head.released
        for head in heads
    )
    assert (
        fixture.store.current(
            "journal"
        )
        is None
    )
    assert (
        fixture.store.current(
            "receipts"
        )
        is None
    )


@pytest.mark.parametrize(
    "chain_ids",
    [
        ("journal",),
        ("journal", "journal"),
    ],
)
def test_acquire_many_requires_two_unique_chains(chain_ids):
    fixture = Fixture()
    with pytest.raises(
        ValueError,
        match="unique",
    ):
        fixture.store.acquire_many(
            chain_ids,
            holder_id="group-a",
            operator_id="operator",
        )


def test_acquire_many_renew_must_be_bool():
    fixture = Fixture()
    with pytest.raises(
        ValueError,
        match="renew",
    ):
        fixture.store.acquire_many(
            ("journal", "receipts"),
            holder_id="group-a",
            operator_id="operator",
            renew="yes",
        )


class ConflictOnceBackend(
    InMemoryFencedStore
):
    def __init__(self):
        super().__init__()
        self.conflicted = False

    def compare_and_swap(
        self,
        namespace,
        key,
        *,
        expected_revision,
        value,
    ):
        if (
            namespace == "reservations"
            and key.startswith("head:")
            and not self.conflicted
        ):
            self.conflicted = True
            raise DistributedStateConflict(
                "synthetic reservation race"
            )
        return super().compare_and_swap(
            namespace,
            key,
            expected_revision=expected_revision,
            value=value,
        )


def test_acquire_retries_head_cas_conflict():
    backend = ConflictOnceBackend()
    fixture = Fixture(
        backend=backend
    )
    item = fixture.acquire()
    assert backend.conflicted
    assert (
        item.reservation.generation
        == 1
    )
    assert (
        fixture.store.current(
            "journal"
        )
        == item
    )


class AlwaysConflictBackend(
    InMemoryFencedStore
):
    def compare_and_swap(
        self,
        namespace,
        key,
        *,
        expected_revision,
        value,
    ):
        if (
            namespace == "reservations"
            and key.startswith("head:")
        ):
            raise DistributedStateConflict(
                "always"
            )
        return super().compare_and_swap(
            namespace,
            key,
            expected_revision=expected_revision,
            value=value,
        )


def test_acquire_honors_retry_bound():
    backend = AlwaysConflictBackend()
    store = (
        DurableCompactionReservationStore(
            backend,
            ArtifactSigner(
                "reservation",
                b"r" * 32,
            ),
            namespace="reservations",
            max_cas_retries=2,
        )
    )
    with pytest.raises(
        DurableCompactionReservationError,
        match="retry budget",
    ):
        store.acquire(
            "journal",
            holder_id="group",
            operator_id="operator",
        )


@pytest.mark.parametrize(
    "namespace",
    ["", "x" * 129],
)
def test_namespace_validation(namespace):
    with pytest.raises(
        ValueError,
        match="namespace",
    ):
        DurableCompactionReservationStore(
            InMemoryFencedStore(),
            ArtifactSigner(
                "reservation",
                b"r" * 32,
            ),
            namespace=namespace,
        )


@pytest.mark.parametrize(
    "ttl,max_ttl",
    [
        (0, 60),
        (-1, 60),
        (61, 60),
        (float("nan"), 60),
        (10, 0),
    ],
)
def test_ttl_constructor_validation(
    ttl,
    max_ttl,
):
    with pytest.raises(ValueError):
        DurableCompactionReservationStore(
            InMemoryFencedStore(),
            ArtifactSigner(
                "reservation",
                b"r" * 32,
            ),
            ttl_seconds=ttl,
            max_ttl_seconds=max_ttl,
        )


@pytest.mark.parametrize(
    "ttl",
    [0, -1, 3601, float("nan")],
)
def test_acquire_ttl_validation(ttl):
    fixture = Fixture()
    with pytest.raises(
        ValueError,
        match="ttl",
    ):
        fixture.acquire(
            ttl_seconds=ttl,
        )


@pytest.mark.parametrize(
    "retries",
    [0, 129, True],
)
def test_retry_bound_validation(retries):
    with pytest.raises(
        ValueError,
        match="max_cas_retries",
    ):
        DurableCompactionReservationStore(
            InMemoryFencedStore(),
            ArtifactSigner(
                "reservation",
                b"r" * 32,
            ),
            max_cas_retries=retries,
        )


def test_invalid_clock_blocks_acquire():
    store = DurableCompactionReservationStore(
        InMemoryFencedStore(),
        ArtifactSigner(
            "reservation",
            b"r" * 32,
        ),
        clock=lambda: float("nan"),
    )
    with pytest.raises(
        DurableCompactionReservationError,
        match="clock",
    ):
        store.acquire(
            "journal",
            holder_id="group",
            operator_id="operator",
        )


def test_invalid_nonce_blocks_acquire():
    store = DurableCompactionReservationStore(
        InMemoryFencedStore(),
        ArtifactSigner(
            "reservation",
            b"r" * 32,
        ),
        nonce_factory=lambda: "",
    )
    with pytest.raises(
        ValueError,
        match="nonce",
    ):
        store.acquire(
            "journal",
            holder_id="group",
            operator_id="operator",
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("reservation_id", "bad"),
        ("chain_id", ""),
        ("holder_id", ""),
        ("operator_id", ""),
        ("generation", 0),
        ("nonce", ""),
        ("issued_at", -1.0),
        ("expires_at", -1.0),
    ],
)
def test_reservation_dataclass_validation(
    field,
    value,
):
    values = dict(
        schema_version=1,
        reservation_id=fp(
            "reservation"
        ),
        chain_id="journal",
        holder_id="group",
        operator_id="operator",
        generation=1,
        nonce="nonce",
        issued_at=1.0,
        expires_at=2.0,
    )
    values[field] = value
    with pytest.raises(ValueError):
        DurableCompactionReservation(
            **values
        )


def test_reservation_rejects_non_forward_expiry():
    with pytest.raises(
        ValueError,
        match="expiry",
    ):
        DurableCompactionReservation(
            1,
            fp("reservation"),
            "journal",
            "group",
            "operator",
            1,
            "nonce",
            2.0,
            2.0,
        )


def test_reservation_id_is_deterministic_for_exact_inputs():
    kwargs = dict(
        chain_id="journal",
        holder_id="group",
        operator_id="operator",
        generation=1,
        nonce="nonce",
        issued_at=1.0,
        expires_at=2.0,
    )
    first = (
        DurableCompactionReservation
        .derive_id(**kwargs)
    )
    second = (
        DurableCompactionReservation
        .derive_id(**kwargs)
    )
    assert first == second
    assert len(first) == 64


def test_reservation_id_changes_with_generation():
    base = dict(
        chain_id="journal",
        holder_id="group",
        operator_id="operator",
        nonce="nonce",
        issued_at=1.0,
        expires_at=2.0,
    )
    assert (
        DurableCompactionReservation
        .derive_id(
            **base,
            generation=1,
        )
        != DurableCompactionReservation
        .derive_id(
            **base,
            generation=2,
        )
    )


def test_signed_reservation_type_validation():
    with pytest.raises(TypeError):
        SignedDurableCompactionReservation(
            object(),
            SignedArtifact(
                "x",
                fp("x"),
                "key",
                1.0,
                {},
                fp("sig"),
            ),
        )


def test_head_validation():
    with pytest.raises(ValueError):
        DurableCompactionReservationHead(
            "",
            fp("id"),
            1,
        )
    with pytest.raises(ValueError):
        DurableCompactionReservationHead(
            "journal",
            "bad",
            1,
        )
    with pytest.raises(ValueError):
        DurableCompactionReservationHead(
            "journal",
            fp("id"),
            0,
        )
    with pytest.raises(ValueError):
        DurableCompactionReservationHead(
            "journal",
            fp("id"),
            1,
            -1.0,
        )


def test_status_serialization():
    status = (
        DurableCompactionReservationStatus(
            "journal",
            True,
            False,
            False,
            "group",
            "operator",
            fp("reservation"),
            2,
            10.0,
        )
    )
    data = status.to_dict()
    assert data["active"] is True
    assert data["holder_id"] == "group"
    assert data["generation"] == 2


def test_reservation_serialization_declares_non_destructive_authority():
    fixture = Fixture()
    item = fixture.acquire()
    data = item.to_dict()
    assert (
        data[
            "destructive_action_authorized"
        ]
        is False
    )
    assert (
        data["reservation"][
            "destructive_action_authorized"
        ]
        is False
    )
    assert (
        data["reservation"]["digest"]
        == item.reservation.digest
    )
