"""Health and admission tests for durable destruction evidence."""

from __future__ import annotations

from dataclasses import replace
import hashlib

import pytest

from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_destruction import (
    DESTRUCTION_ARTIFACT_TYPE,
    DurableDestructionHead,
    DurableDestructionItem,
    DurableDestructionIndexState,
    DurableDestructionItemState,
    DurableDestructionKind,
    DurableDestructionLedger,
)
from skeleton.shells.ai.durable_destruction_health import (
    DurableDestructionChainHealth,
    DurableDestructionFleetHealth,
    DurableDestructionHealthError,
    DurableDestructionHealthFinding,
    DurableDestructionHealthGuard,
    DurableDestructionHealthPolicy,
    DurableDestructionHealthSeverity,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner


def fp(char: str) -> str:
    if len(char) == 1 and char.lower() in "0123456789abcdef":
        return char.lower() * 64
    return hashlib.sha256(char.encode()).hexdigest()


def make_ledger(
    backend=None,
    *,
    namespace="destruction",
):
    backend = backend or InMemoryFencedStore()
    return DurableDestructionLedger(
        backend,
        ArtifactSigner(
            "destruction-health",
            b"h" * 32,
            clock=lambda: 100.0,
        ),
        namespace=namespace,
        clock=lambda: 100.0,
    )


def destruction_item(
    suffix: str,
    *,
    archived=True,
):
    return DurableDestructionItem(
        "journal_event",
        "journal",
        f"event:{suffix}",
        fp(suffix[0]),
        DurableDestructionItemState.DELETED,
        1,
        1,
        "",
        archived,
    )


def append_pruning(
    ledger,
    *,
    operation_char="o",
    item_char="a",
    completed_at=100.0,
    verified=True,
):
    return ledger.append(
        chain_id="journal",
        operation_kind=DurableDestructionKind.PRUNING,
        operation_id=fp(operation_char),
        authority_id=fp("a"),
        authority_digest=fp("b"),
        manifest_digest=fp("m"),
        before_sequence=5,
        before_root=fp("r"),
        before_floor_sequence=0,
        before_floor_root="0" * 64,
        after_sequence=5,
        after_root=fp("r"),
        after_floor_sequence=3,
        after_floor_root=fp("f"),
        items=(
            destruction_item(item_char),
        ),
        archive_id="archive",
        archive_manifest_digest=fp("c"),
        post_verify_digest=(
            fp("v") if verified else ""
        ),
        post_verified=verified,
        fencing_token=1,
        completed_at=completed_at,
    )


def append_gc(
    ledger,
    *,
    chain_id="journal",
    operation_char="g",
    item_char="q",
    completed_at=101.0,
    verified=True,
):
    item = DurableDestructionItem(
        "journal_event",
        "journal",
        f"event:{item_char}",
        fp(item_char),
        DurableDestructionItemState.DELETED,
        2,
        2,
        "",
        False,
    )
    return ledger.append(
        chain_id=chain_id,
        operation_kind=DurableDestructionKind.ORPHAN_GC,
        operation_id=fp(operation_char),
        authority_id=fp("z"),
        authority_digest=fp("y"),
        manifest_digest=fp("x"),
        before_sequence=5,
        before_root=fp("r"),
        before_floor_sequence=0,
        before_floor_root="0" * 64,
        after_sequence=5,
        after_root=fp("r"),
        after_floor_sequence=0,
        after_floor_root="0" * 64,
        items=(item,),
        post_verify_digest=(
            fp("w") if verified else ""
        ),
        post_verified=verified,
        fencing_token=2,
        completed_at=completed_at,
    )


def test_empty_history_is_healthy_by_default():
    guard = DurableDestructionHealthGuard(
        make_ledger()
    )
    report = guard.inspect(("journal",))
    assert report.allowed
    assert report.errors == 0
    assert report.records == 0
    assert report.chains[0].ok
    assert report.chains[0].records == 0


def test_nonempty_policy_rejects_empty_history():
    guard = DurableDestructionHealthGuard(
        make_ledger(),
        policy=DurableDestructionHealthPolicy(
            require_nonempty=True,
        ),
    )
    report = guard.inspect(("journal",))
    assert not report.allowed
    assert report.errors == 1
    assert any(
        finding.code
        == "destruction.history.empty"
        for finding in report.chains[0].findings
    )


def test_healthy_pruning_history_is_allowed():
    ledger = make_ledger()
    signed = append_pruning(ledger)
    report = DurableDestructionHealthGuard(
        ledger
    ).inspect(("journal",))
    chain = report.chains[0]
    assert report.allowed
    assert chain.ok
    assert chain.records == 1
    assert chain.pruning_records == 1
    assert chain.orphan_gc_records == 0
    assert chain.verified_records == 1
    assert chain.latest_record_id == signed.record_id
    assert chain.index_health.healthy
    assert chain.verification.ok


def test_mixed_history_counts_operation_kinds():
    ledger = make_ledger()
    append_pruning(ledger)
    append_gc(ledger)
    report = DurableDestructionHealthGuard(
        ledger
    ).inspect(("journal",))
    chain = report.chains[0]
    assert chain.records == 2
    assert chain.pruning_records == 1
    assert chain.orphan_gc_records == 1
    assert chain.verified_records == 2
    assert report.allowed


def test_multiple_chains_are_sorted_and_aggregated():
    ledger = make_ledger()
    append_pruning(ledger)
    append_gc(
        ledger,
        chain_id="receipts",
        operation_char="u",
        item_char="s",
    )
    report = DurableDestructionHealthGuard(
        ledger
    ).inspect(("receipts", "journal"))
    assert tuple(
        item.chain_id
        for item in report.chains
    ) == ("journal", "receipts")
    assert report.records == 2
    assert report.allowed


def test_duplicate_chain_ids_are_rejected():
    guard = DurableDestructionHealthGuard(
        make_ledger()
    )
    with pytest.raises(
        DurableDestructionHealthError,
        match="duplicate",
    ):
        guard.inspect(
            ("journal", "journal")
        )


def test_chain_bound_is_enforced():
    guard = DurableDestructionHealthGuard(
        make_ledger(),
        policy=DurableDestructionHealthPolicy(
            max_chains=1,
        ),
    )
    with pytest.raises(
        DurableDestructionHealthError,
        match="bound",
    ):
        guard.inspect(
            ("journal", "receipts")
        )


def test_invalid_chain_id_is_rejected():
    guard = DurableDestructionHealthGuard(
        make_ledger()
    )
    with pytest.raises(ValueError, match="chain_id"):
        guard.inspect(("",))


def test_require_returns_healthy_report():
    ledger = make_ledger()
    append_pruning(ledger)
    report = DurableDestructionHealthGuard(
        ledger
    ).require(("journal",))
    assert report.allowed
    assert report.records == 1


def test_require_raises_on_empty_required_history():
    guard = DurableDestructionHealthGuard(
        make_ledger(),
        policy=DurableDestructionHealthPolicy(
            require_nonempty=True,
        ),
    )
    with pytest.raises(
        DurableDestructionHealthError,
        match="required",
    ):
        guard.require(("journal",))


def test_missing_operation_index_is_error_by_default():
    backend = InMemoryFencedStore()
    ledger = make_ledger(backend)
    signed = append_pruning(ledger)
    key = ledger._operation_index_key(
        signed.operation_key
    )
    record = backend.get(
        ledger.namespace,
        key,
    )
    backend.delete(
        ledger.namespace,
        key,
        expected_revision=record.revision,
    )
    report = DurableDestructionHealthGuard(
        ledger
    ).inspect(("journal",))
    assert not report.allowed
    assert report.chains[0].index_health.missing_indexes == 1
    assert any(
        item.code
        == "destruction.index.unhealthy"
        for item in report.chains[0].findings
    )


def test_missing_operation_index_can_be_warning_by_policy():
    backend = InMemoryFencedStore()
    ledger = make_ledger(backend)
    signed = append_pruning(ledger)
    key = ledger._operation_index_key(
        signed.operation_key
    )
    record = backend.get(
        ledger.namespace,
        key,
    )
    backend.delete(
        ledger.namespace,
        key,
        expected_revision=record.revision,
    )
    report = DurableDestructionHealthGuard(
        ledger,
        policy=DurableDestructionHealthPolicy(
            require_healthy_indexes=False,
        ),
    ).inspect(("journal",))
    assert report.allowed
    assert report.warnings == 1


def test_repair_indexes_and_require_repairs_missing_index():
    backend = InMemoryFencedStore()
    ledger = make_ledger(backend)
    signed = append_pruning(ledger)
    key = ledger._operation_index_key(
        signed.operation_key
    )
    record = backend.get(
        ledger.namespace,
        key,
    )
    backend.delete(
        ledger.namespace,
        key,
        expected_revision=record.revision,
    )
    guard = DurableDestructionHealthGuard(
        ledger
    )
    report = guard.repair_indexes_and_require(
        ("journal",)
    )
    assert report.allowed
    assert report.chains[0].index_health.healthy
    assert backend.get(
        ledger.namespace,
        key,
    ) is not None


def test_repair_bound_is_enforced():
    backend = InMemoryFencedStore()
    ledger = make_ledger(backend)
    first = append_pruning(ledger)
    second = append_gc(ledger)
    for signed in (first, second):
        key = ledger._operation_index_key(
            signed.operation_key
        )
        record = backend.get(
            ledger.namespace,
            key,
        )
        backend.delete(
            ledger.namespace,
            key,
            expected_revision=record.revision,
        )
    guard = DurableDestructionHealthGuard(
        ledger
    )
    with pytest.raises(Exception):
        guard.repair_indexes_and_require(
            ("journal",),
            max_repairs_per_chain=1,
        )


@pytest.mark.parametrize(
    "bound",
    [0, -1, True],
)
def test_repair_bound_validation(bound):
    guard = DurableDestructionHealthGuard(
        make_ledger()
    )
    with pytest.raises(ValueError):
        guard.repair_indexes_and_require(
            ("journal",),
            max_repairs_per_chain=bound,
        )


def test_signature_tamper_is_health_error():
    backend = InMemoryFencedStore()
    ledger = make_ledger(backend)
    signed = append_pruning(ledger)
    key = ledger._record_key(
        signed.record_id
    )
    stored = backend.get(
        ledger.namespace,
        key,
    )
    raw = dict(stored.value)
    signature = dict(raw["signature"])
    signature["signature"] = "f" * 64
    raw["signature"] = signature
    backend.compare_and_swap(
        ledger.namespace,
        key,
        expected_revision=stored.revision,
        value=raw,
    )
    report = DurableDestructionHealthGuard(
        ledger
    ).inspect(("journal",))
    assert not report.allowed
    assert report.errors >= 1
    assert any(
        item.code.startswith(
            "destruction."
        )
        for item in report.chains[0].findings
    )


def test_missing_committed_record_is_health_error():
    backend = InMemoryFencedStore()
    ledger = make_ledger(backend)
    signed = append_pruning(ledger)
    key = ledger._record_key(
        signed.record_id
    )
    record = backend.get(
        ledger.namespace,
        key,
    )
    backend.delete(
        ledger.namespace,
        key,
        expected_revision=record.revision,
    )
    report = DurableDestructionHealthGuard(
        ledger
    ).inspect(("journal",))
    assert not report.allowed
    assert any(
        item.code
        == "destruction.snapshot.failed"
        for item in report.chains[0].findings
    )


def test_unverified_record_is_error_by_default():
    ledger = make_ledger()
    append_gc(
        ledger,
        verified=False,
    )
    report = DurableDestructionHealthGuard(
        ledger
    ).inspect(("journal",))
    assert not report.allowed
    assert any(
        item.code
        == "destruction.post_verify.missing"
        for item in report.chains[0].findings
    )


def test_unverified_record_can_be_warning_by_policy():
    ledger = make_ledger()
    append_gc(
        ledger,
        verified=False,
    )
    report = DurableDestructionHealthGuard(
        ledger,
        policy=DurableDestructionHealthPolicy(
            require_post_verified=False,
        ),
    ).inspect(("journal",))
    assert report.allowed
    assert report.warnings == 1


def test_record_pressure_warns_at_threshold():
    ledger = make_ledger()
    append_pruning(ledger)
    append_gc(ledger)
    guard = DurableDestructionHealthGuard(
        ledger,
        policy=DurableDestructionHealthPolicy(
            max_records_per_chain=2,
            warn_records_at_fraction=1.0,
        ),
    )
    report = guard.inspect(("journal",))
    assert report.allowed
    assert any(
        item.code
        == "destruction.records.pressure"
        for item in report.chains[0].findings
    )


def test_record_bound_exceeded_is_error():
    ledger = make_ledger()
    append_pruning(ledger)
    append_gc(ledger)
    guard = DurableDestructionHealthGuard(
        ledger,
        policy=DurableDestructionHealthPolicy(
            max_records_per_chain=1,
            warn_records_at_fraction=1.0,
        ),
    )
    report = guard.inspect(("journal",))
    assert not report.allowed
    assert any(
        item.code
        == "destruction.records.bound_exceeded"
        for item in report.chains[0].findings
    )


def test_policy_digest_is_stable():
    first = DurableDestructionHealthPolicy()
    second = DurableDestructionHealthPolicy()
    assert first.digest == second.digest
    assert len(first.digest) == 64


@pytest.mark.parametrize(
    "name,value",
    [
        ("max_chains", 0),
        ("max_findings", 0),
        ("max_records_per_chain", 0),
    ],
)
def test_policy_positive_integer_validation(name, value):
    with pytest.raises(ValueError):
        DurableDestructionHealthPolicy(
            **{name: value}
        )


@pytest.mark.parametrize(
    "value",
    [0.0, -0.1, 1.1, True],
)
def test_policy_warning_fraction_validation(value):
    with pytest.raises(ValueError):
        DurableDestructionHealthPolicy(
            warn_records_at_fraction=value
        )


@pytest.mark.parametrize(
    "name",
    [
        "require_nonempty",
        "require_healthy_indexes",
        "require_post_verified",
    ],
)
def test_policy_boolean_validation(name):
    with pytest.raises(ValueError):
        DurableDestructionHealthPolicy(
            **{name: "yes"}
        )


def test_finding_serialization():
    finding = DurableDestructionHealthFinding(
        DurableDestructionHealthSeverity.ERROR,
        "code",
        "message",
        "journal",
        fp("a"),
    )
    assert finding.to_dict() == {
        "severity": "error",
        "code": "code",
        "message": "message",
        "chain_id": "journal",
        "record_id": fp("a"),
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"code": ""},
        {"message": ""},
        {"chain_id": "x" * 129},
        {"record_id": "bad"},
    ],
)
def test_finding_validation(kwargs):
    values = dict(
        severity=DurableDestructionHealthSeverity.ERROR,
        code="code",
        message="message",
        chain_id="journal",
        record_id=fp("a"),
    )
    values.update(kwargs)
    with pytest.raises(ValueError):
        DurableDestructionHealthFinding(
            **values
        )


def test_chain_health_digest_and_serialization():
    ledger = make_ledger()
    append_pruning(ledger)
    chain = DurableDestructionHealthGuard(
        ledger
    ).inspect(("journal",)).chains[0]
    data = chain.to_dict()
    assert data["ok"] is True
    assert data["records"] == 1
    assert data["pruning_records"] == 1
    assert data["orphan_gc_records"] == 0
    assert data["digest"] == chain.digest
    assert len(chain.digest) == 64


def test_fleet_health_digest_is_stable():
    ledger = make_ledger()
    append_pruning(ledger)
    guard = DurableDestructionHealthGuard(
        ledger
    )
    first = guard.inspect(("journal",))
    second = guard.inspect(("journal",))
    assert first.digest == second.digest
    assert first == second


def test_fleet_serialization():
    ledger = make_ledger()
    append_pruning(ledger)
    report = DurableDestructionHealthGuard(
        ledger
    ).inspect(("journal",))
    data = report.to_dict()
    assert data["allowed"] is True
    assert data["records"] == 1
    assert data["policy_digest"] == report.policy_digest
    assert data["digest"] == report.digest
    assert len(data["chains"]) == 1


def test_guard_constructor_rejects_wrong_ledger():
    with pytest.raises(TypeError, match="ledger"):
        DurableDestructionHealthGuard(
            object()
        )


def test_guard_constructor_rejects_wrong_policy():
    with pytest.raises(TypeError, match="policy"):
        DurableDestructionHealthGuard(
            make_ledger(),
            policy=object(),
        )


def test_empty_fleet_allowed_by_default():
    report = DurableDestructionHealthGuard(
        make_ledger()
    ).inspect(())
    assert report.allowed
    assert report.chains == ()
    assert report.records == 0


def test_empty_fleet_rejected_when_nonempty_required():
    report = DurableDestructionHealthGuard(
        make_ledger(),
        policy=DurableDestructionHealthPolicy(
            require_nonempty=True,
        ),
    ).inspect(())
    assert not report.allowed
    assert report.findings[0].code == "destruction.fleet.empty"


def test_findings_bound_truncates_and_fails_closed():
    ledger = make_ledger()
    for index, char in enumerate(
        ("a", "b", "c", "d"),
        start=1,
    ):
        append_gc(
            ledger,
            operation_char=char,
            item_char=char,
            completed_at=100.0 + index,
            verified=False,
        )
    report = DurableDestructionHealthGuard(
        ledger,
        policy=DurableDestructionHealthPolicy(
            max_findings=2,
        ),
    ).inspect(("journal",))
    chain = report.chains[0]
    assert not report.allowed
    assert len(chain.findings) == 3
    assert chain.findings[-1].code == "destruction.findings.truncated"


def test_index_health_inspection_reports_healthy_record():
    ledger = make_ledger()
    append_pruning(ledger)
    health = ledger.inspect_operation_indexes(
        "journal"
    )
    assert health.healthy
    assert health.records == 1
    assert health.healthy_indexes == 1
    assert health.missing_indexes == 0
    assert health.corrupt_indexes == 0
    assert health.uncommitted_indexes == 0


def test_index_health_reports_missing_index_repairable():
    backend = InMemoryFencedStore()
    ledger = make_ledger(backend)
    signed = append_pruning(ledger)
    key = ledger._operation_index_key(
        signed.operation_key
    )
    stored = backend.get(
        ledger.namespace,
        key,
    )
    backend.delete(
        ledger.namespace,
        key,
        expected_revision=stored.revision,
    )
    health = ledger.inspect_operation_indexes(
        "journal"
    )
    assert not health.healthy
    assert health.repairable
    assert health.missing_indexes == 1
    assert health.findings[0].state is (
        DurableDestructionIndexState.MISSING
    )


def test_index_repair_restores_health():
    backend = InMemoryFencedStore()
    ledger = make_ledger(backend)
    signed = append_pruning(ledger)
    key = ledger._operation_index_key(
        signed.operation_key
    )
    stored = backend.get(
        ledger.namespace,
        key,
    )
    backend.delete(
        ledger.namespace,
        key,
        expected_revision=stored.revision,
    )
    health = ledger.repair_operation_indexes(
        "journal"
    )
    assert health.healthy
    assert health.records == 1


def test_index_repair_noop_when_healthy():
    ledger = make_ledger()
    append_pruning(ledger)
    before = ledger.inspect_operation_indexes(
        "journal"
    )
    after = ledger.repair_operation_indexes(
        "journal"
    )
    assert after == before


@pytest.mark.parametrize(
    "value",
    [0, -1, True],
)
def test_ledger_index_repair_bound_validation(value):
    ledger = make_ledger()
    with pytest.raises(ValueError, match="max_repairs"):
        ledger.repair_operation_indexes(
            "journal",
            max_repairs=value,
        )


def test_corrupt_index_is_not_marked_repairable():
    backend = InMemoryFencedStore()
    ledger = make_ledger(backend)
    signed = append_pruning(ledger)
    key = ledger._operation_index_key(
        signed.operation_key
    )
    stored = backend.get(
        ledger.namespace,
        key,
    )
    raw = dict(stored.value)
    raw["record_digest"] = fp("z")
    backend.compare_and_swap(
        ledger.namespace,
        key,
        expected_revision=stored.revision,
        value=raw,
    )
    health = ledger.inspect_operation_indexes(
        "journal"
    )
    assert not health.healthy
    assert not health.repairable
    assert health.corrupt_indexes == 1


def test_repair_does_not_overwrite_corrupt_index():
    backend = InMemoryFencedStore()
    ledger = make_ledger(backend)
    signed = append_pruning(ledger)
    key = ledger._operation_index_key(
        signed.operation_key
    )
    stored = backend.get(
        ledger.namespace,
        key,
    )
    raw = dict(stored.value)
    raw["record_digest"] = fp("z")
    backend.compare_and_swap(
        ledger.namespace,
        key,
        expected_revision=stored.revision,
        value=raw,
    )
    after = ledger.repair_operation_indexes(
        "journal"
    )
    assert not after.healthy
    assert after.corrupt_indexes == 1


def test_health_report_reflects_repaired_index():
    backend = InMemoryFencedStore()
    ledger = make_ledger(backend)
    signed = append_pruning(ledger)
    key = ledger._operation_index_key(
        signed.operation_key
    )
    stored = backend.get(
        ledger.namespace,
        key,
    )
    backend.delete(
        ledger.namespace,
        key,
        expected_revision=stored.revision,
    )
    guard = DurableDestructionHealthGuard(
        ledger
    )
    assert not guard.inspect(
        ("journal",)
    ).allowed
    repaired = guard.repair_indexes_and_require(
        ("journal",)
    )
    assert repaired.allowed
    assert repaired.chains[0].index_health.healthy


def test_health_severity_wire_values_are_stable():
    assert {
        item.value
        for item in DurableDestructionHealthSeverity
    } == {
        "info",
        "warning",
        "error",
    }
