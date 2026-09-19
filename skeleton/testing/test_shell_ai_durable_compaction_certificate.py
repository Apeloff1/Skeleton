"""Signed non-destructive durable compaction readiness certificate tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_journal import (
    DistributedAIDecisionJournal,
)
from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.durable_archive import DurableArchiveManifestBuilder
from skeleton.shells.ai.durable_archive_store import DurableArchiveRepository
from skeleton.shells.ai.durable_checkpoint import DurableChainCheckpointStore
from skeleton.shells.ai.durable_compaction import (
    DurableCompactionPlanner,
    DurableCompactionPolicy,
)
from skeleton.shells.ai.durable_compaction_certificate import (
    DurableCompactionCertificate,
    DurableCompactionCertificateError,
    DurableCompactionCertificateHead,
    DurableCompactionCertificateStore,
    DurableCompactionCertificateVerification,
    SignedDurableCompactionCertificate,
)
from skeleton.shells.ai.durable_retention import (
    DurableRetentionPlanner,
    DurableRetentionPolicy,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner


def fp(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode()).hexdigest()


def append_events(journal, count, *, start=0):
    result = []
    for index in range(start, start + count):
        result.append(
            journal.append(
                "certificate.event",
                session_id=f"session-{index}",
                intent_id=f"intent-{index}",
                proposal_id=f"proposal-{index}",
                summary=f"event {index}",
            )
        )
    return tuple(result)


class Fixture:
    def __init__(
        self,
        *,
        now=400.0,
        ttl=60.0,
        compaction_policy=None,
    ):
        self.now = [float(now)]
        self.backend = InMemoryFencedStore()
        self.journal = DistributedAIDecisionJournal(
            self.backend,
            namespace="journal",
            max_events=20,
            clock=lambda: 10.0,
        )
        self.checkpoint_signer = ArtifactSigner(
            "checkpoint",
            b"c" * 32,
            clock=lambda: 100.0,
        )
        self.archive_signer = ArtifactSigner(
            "archive",
            b"a" * 32,
            clock=lambda: 200.0,
        )
        self.certificate_signer = ArtifactSigner(
            "certificate",
            b"s" * 32,
            clock=lambda: self.now[0],
        )
        self.checkpoints = DurableChainCheckpointStore(
            self.backend,
            self.checkpoint_signer,
            namespace="checkpoints",
            clock=lambda: 100.0,
        )
        self.archive_builder = DurableArchiveManifestBuilder(
            self.checkpoints,
            self.archive_signer,
            clock=lambda: 200.0,
        )
        self.archives = DurableArchiveRepository(
            self.backend,
            self.checkpoints,
            self.archive_signer,
            namespace="archives",
            clock=lambda: 300.0,
        )
        self.retention_planner = DurableRetentionPlanner(
            self.checkpoints,
            DurableRetentionPolicy(
                minimum_live_tail=2,
                minimum_archive_batch=2,
                target_utilization=0.25,
                warning_utilization=0.75,
                critical_utilization=0.95,
                max_protected_roots=32,
            ),
        )
        self.compaction = DurableCompactionPlanner(
            self.archives,
            compaction_policy
            or DurableCompactionPolicy(
                minimum_live_tail=2,
                maximum_candidate_nodes=20,
                max_protected_roots=32,
            ),
        )
        self.store = DurableCompactionCertificateStore(
            self.backend,
            self.certificate_signer,
            self.compaction,
            namespace="certificates",
            ttl_seconds=ttl,
            max_ttl_seconds=3600.0,
            clock=lambda: self.now[0],
        )
        self.first = append_events(
            self.journal,
            6,
        )
        checkpoint = self.checkpoints.publish(
            "journal",
            self.journal,
        )
        archive = self.archive_builder.build(
            checkpoint,
            self.journal,
        )
        self.archives.put(
            archive,
            checkpoint,
            self.journal,
        )
        self.later = append_events(
            self.journal,
            2,
            start=6,
        )
        self.retention = self.retention_planner.plan(
            "journal",
            self.journal,
        )
        assert self.compaction.require_ready(
            self.retention,
            self.journal,
        ).ready

    def issue(self, **kwargs):
        return self.store.issue(
            self.retention,
            self.journal,
            **kwargs,
        )


def test_issue_signed_current_certificate():
    fixture = Fixture()
    item = fixture.issue()
    cert = item.certificate
    assert cert.chain_id == "journal"
    assert cert.current_sequence == 8
    assert cert.current_root == fixture.later[-1].event_hash
    assert cert.cutoff_sequence == 6
    assert cert.cutoff_root == fixture.first[-1].event_hash
    assert cert.archive_id
    assert len(cert.archive_manifest_digest) == 64
    assert len(cert.protected_roots_digest) == 64
    assert cert.issued_at == 400.0
    assert cert.expires_at == 460.0
    assert not cert.destructive_action_authorized
    assert not item.destructive_action_authorized
    assert (
        item.signature.metadata["authority"]
        == "non-destructive-compaction-readiness"
    )


def test_certificate_signature_verifies_current_readiness():
    fixture = Fixture()
    item = fixture.issue()
    report = fixture.store.require_current(
        item,
        fixture.retention,
        fixture.journal,
    )
    assert report.valid
    assert report.current
    assert not report.expired
    assert report.allowed
    assert not report.destructive_action_authorized
    assert report.reasons == ()


def test_issue_reuses_valid_matching_certificate():
    fixture = Fixture()
    first = fixture.issue()
    fixture.now[0] = 420.0
    second = fixture.issue()
    assert second == first
    assert second.certificate_id == first.certificate_id
    assert second.certificate.issued_at == 400.0


def test_expired_matching_readiness_can_be_renewed():
    fixture = Fixture(ttl=10.0)
    first = fixture.issue()
    fixture.now[0] = 411.0
    second = fixture.issue()
    assert second.certificate_id != first.certificate_id
    assert second.certificate.issued_at == 411.0
    assert second.certificate.expires_at == 421.0
    assert (
        second.certificate.readiness_digest
        == first.certificate.readiness_digest
    )
    assert (
        fixture.store.latest("journal")
        == second
    )


def test_expired_old_certificate_remains_retrievable():
    fixture = Fixture(ttl=10.0)
    first = fixture.issue()
    fixture.now[0] = 411.0
    fixture.issue()
    restored = fixture.store.get(
        first.certificate_id
    )
    assert restored == first
    report = fixture.store.inspect(
        restored,
        fixture.retention,
        fixture.journal,
    )
    assert report.valid
    assert report.current
    assert report.expired
    assert not report.allowed


def test_require_current_rejects_expired_certificate():
    fixture = Fixture(ttl=10.0)
    item = fixture.issue()
    fixture.now[0] = 410.0
    with pytest.raises(
        DurableCompactionCertificateError,
        match="expired",
    ):
        fixture.store.require_current(
            item,
            fixture.retention,
            fixture.journal,
        )


def test_chain_growth_stales_certificate():
    fixture = Fixture()
    item = fixture.issue()
    append_events(
        fixture.journal,
        1,
        start=8,
    )
    report = fixture.store.inspect(
        item,
        fixture.retention,
        fixture.journal,
    )
    assert report.valid
    assert not report.current
    assert not report.allowed
    assert any(
        "no longer matches" in reason
        for reason in report.reasons
    )


def test_changed_retention_plan_stales_certificate():
    fixture = Fixture()
    item = fixture.issue()
    protected = fixture.first[1].event_hash
    changed = fixture.retention_planner.plan(
        "journal",
        fixture.journal,
        protected_roots=(protected,),
    )
    assert changed.digest != fixture.retention.digest
    report = fixture.store.inspect(
        item,
        changed,
        fixture.journal,
    )
    assert not report.current
    assert not report.allowed


def test_archive_tamper_stales_certificate():
    fixture = Fixture()
    item = fixture.issue()
    root = fixture.retention.archive_through_root
    key = fixture.archives._node_key(
        "journal",
        root,
    )
    record = fixture.backend.get(
        fixture.archives.namespace,
        key,
    )
    raw = dict(record.value)
    payload = dict(raw["payload"])
    payload["summary"] = "tampered"
    raw["payload"] = payload
    fixture.backend.compare_and_swap(
        fixture.archives.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    report = fixture.store.inspect(
        item,
        fixture.retention,
        fixture.journal,
    )
    assert report.valid
    assert not report.current
    assert not report.allowed


def test_missing_archive_stales_certificate():
    fixture = Fixture()
    item = fixture.issue()
    archive = fixture.archives.require(
        item.certificate.archive_id
    )
    key = fixture.archives._archive_key(
        archive.manifest.manifest.archive_id
    )
    record = fixture.backend.get(
        fixture.archives.namespace,
        key,
    )
    fixture.backend.delete(
        fixture.archives.namespace,
        key,
        expected_revision=record.revision,
    )
    report = fixture.store.inspect(
        item,
        fixture.retention,
        fixture.journal,
    )
    assert not report.current


def test_fresh_store_reader_verifies_certificate():
    fixture = Fixture()
    item = fixture.issue()
    fresh = DurableCompactionCertificateStore(
        fixture.backend,
        ArtifactSigner(
            "certificate",
            b"s" * 32,
            clock=lambda: fixture.now[0],
        ),
        fixture.compaction,
        namespace="certificates",
        ttl_seconds=60.0,
        clock=lambda: fixture.now[0],
    )
    restored = fresh.get(
        item.certificate_id
    )
    assert restored == item
    assert fresh.require_current(
        restored,
        fixture.retention,
        fixture.journal,
    ).allowed


def test_wrong_signer_cannot_read_certificate():
    fixture = Fixture()
    item = fixture.issue()
    wrong = DurableCompactionCertificateStore(
        fixture.backend,
        ArtifactSigner(
            "wrong",
            b"w" * 32,
        ),
        fixture.compaction,
        namespace="certificates",
    )
    with pytest.raises(
        DurableCompactionCertificateError,
        match="signature verification",
    ):
        wrong.get(
            item.certificate_id
        )


def test_tampered_signature_is_rejected():
    fixture = Fixture()
    item = fixture.issue()
    key = fixture.store._certificate_key(
        item.certificate_id
    )
    record = fixture.backend.get(
        fixture.store.namespace,
        key,
    )
    raw = dict(record.value)
    signature = dict(raw["signature"])
    signature["signature"] = "f" * 64
    raw["signature"] = signature
    fixture.backend.compare_and_swap(
        fixture.store.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    with pytest.raises(
        DurableCompactionCertificateError,
        match="signature verification",
    ):
        fixture.store.get(
            item.certificate_id
        )


def test_tampered_certificate_payload_is_rejected():
    fixture = Fixture()
    item = fixture.issue()
    key = fixture.store._certificate_key(
        item.certificate_id
    )
    record = fixture.backend.get(
        fixture.store.namespace,
        key,
    )
    raw = dict(record.value)
    certificate = dict(
        raw["certificate"]
    )
    certificate["cutoff_sequence"] += 1
    raw["certificate"] = certificate
    fixture.backend.compare_and_swap(
        fixture.store.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    with pytest.raises(
        DurableCompactionCertificateError,
    ):
        fixture.store.get(
            item.certificate_id
        )


def test_tampered_signature_metadata_is_rejected():
    fixture = Fixture()
    item = fixture.issue()
    key = fixture.store._certificate_key(
        item.certificate_id
    )
    record = fixture.backend.get(
        fixture.store.namespace,
        key,
    )
    raw = dict(record.value)
    signature = dict(raw["signature"])
    metadata = dict(
        signature["metadata"]
    )
    metadata["authority"] = "destructive"
    signature["metadata"] = metadata
    raw["signature"] = signature
    fixture.backend.compare_and_swap(
        fixture.store.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    with pytest.raises(
        DurableCompactionCertificateError,
        match="metadata",
    ):
        fixture.store.get(
            item.certificate_id
        )


def test_latest_tracks_renewed_certificate():
    fixture = Fixture(ttl=5.0)
    first = fixture.issue()
    assert fixture.store.latest(
        "journal"
    ) == first
    fixture.now[0] = 406.0
    second = fixture.issue()
    assert second != first
    assert fixture.store.latest(
        "journal"
    ) == second


def test_latest_missing_chain_returns_none():
    fixture = Fixture()
    assert fixture.store.latest(
        "missing"
    ) is None


def test_get_missing_certificate_returns_none():
    fixture = Fixture()
    assert fixture.store.get(
        fp("missing")
    ) is None


def test_issue_custom_ttl():
    fixture = Fixture()
    item = fixture.issue(
        ttl_seconds=30.0,
    )
    assert (
        item.certificate.expires_at
        - item.certificate.issued_at
        == 30.0
    )


@pytest.mark.parametrize(
    "ttl",
    [0, -1, float("inf"), 4000],
)
def test_issue_ttl_validation(ttl):
    fixture = Fixture()
    with pytest.raises(
        ValueError,
        match="ttl",
    ):
        fixture.issue(
            ttl_seconds=ttl,
        )


@pytest.mark.parametrize(
    "ttl,max_ttl",
    [
        (0, 10),
        (-1, 10),
        (10, 0),
        (20, 10),
        (True, 10),
    ],
)
def test_store_ttl_constructor_validation(ttl, max_ttl):
    fixture = Fixture()
    with pytest.raises(ValueError):
        DurableCompactionCertificateStore(
            fixture.backend,
            fixture.certificate_signer,
            fixture.compaction,
            ttl_seconds=ttl,
            max_ttl_seconds=max_ttl,
        )


@pytest.mark.parametrize(
    "retries",
    [0, 129, True, 1.5],
)
def test_store_retry_bound_validation(retries):
    fixture = Fixture()
    with pytest.raises(
        ValueError,
        match="max_cas_retries",
    ):
        DurableCompactionCertificateStore(
            fixture.backend,
            fixture.certificate_signer,
            fixture.compaction,
            max_cas_retries=retries,
        )


@pytest.mark.parametrize(
    "namespace",
    ["", "x" * 129],
)
def test_store_namespace_validation(namespace):
    fixture = Fixture()
    with pytest.raises(
        ValueError,
        match="namespace",
    ):
        DurableCompactionCertificateStore(
            fixture.backend,
            fixture.certificate_signer,
            fixture.compaction,
            namespace=namespace,
        )


def test_store_constructor_type_validation():
    fixture = Fixture()
    with pytest.raises(TypeError, match="backend"):
        DurableCompactionCertificateStore(
            object(),
            fixture.certificate_signer,
            fixture.compaction,
        )
    with pytest.raises(TypeError, match="signer"):
        DurableCompactionCertificateStore(
            fixture.backend,
            object(),
            fixture.compaction,
        )
    with pytest.raises(TypeError, match="planner"):
        DurableCompactionCertificateStore(
            fixture.backend,
            fixture.certificate_signer,
            object(),
        )
    with pytest.raises(TypeError, match="clock"):
        DurableCompactionCertificateStore(
            fixture.backend,
            fixture.certificate_signer,
            fixture.compaction,
            clock=object(),
        )


def test_invalid_clock_blocks_issue():
    fixture = Fixture()
    store = DurableCompactionCertificateStore(
        fixture.backend,
        fixture.certificate_signer,
        fixture.compaction,
        namespace="bad-clock",
        clock=lambda: float("nan"),
    )
    with pytest.raises(
        DurableCompactionCertificateError,
        match="clock",
    ):
        store.issue(
            fixture.retention,
            fixture.journal,
        )


def test_nonready_compaction_cannot_be_certified():
    fixture = Fixture()
    append_events(
        fixture.journal,
        1,
        start=8,
    )
    with pytest.raises(Exception):
        fixture.store.issue(
            fixture.retention,
            fixture.journal,
        )


def test_certificate_id_changes_with_issue_window():
    fixture = Fixture()
    first = fixture.issue()
    fixture.now[0] = 500.0
    second = fixture.issue()
    assert first.certificate_id != second.certificate_id


def test_certificate_id_is_stable_for_same_full_binding():
    kwargs = dict(
        chain_id="journal",
        readiness_digest=fp("readiness"),
        retention_plan_digest=fp("retention"),
        compaction_policy_digest=fp("policy"),
        current_sequence=8,
        current_root=fp("current"),
        cutoff_sequence=6,
        cutoff_root=fp("cutoff"),
        archive_id="archive",
        archive_manifest_digest=fp("manifest"),
        protected_roots_digest=fp("protected"),
        issued_at=100.0,
        expires_at=200.0,
    )
    first = DurableCompactionCertificate.derive_id(
        **kwargs
    )
    second = DurableCompactionCertificate.derive_id(
        **kwargs
    )
    assert first == second
    assert len(first) == 64


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("certificate_id", "bad"),
        ("chain_id", ""),
        ("readiness_digest", "bad"),
        ("retention_plan_digest", "bad"),
        ("compaction_policy_digest", "bad"),
        ("current_sequence", -1),
        ("current_root", "bad"),
        ("cutoff_sequence", 0),
        ("cutoff_root", "bad"),
        ("archive_id", ""),
        ("archive_manifest_digest", "bad"),
        ("protected_roots_digest", "bad"),
        ("issued_at", -1),
        ("expires_at", -1),
    ],
)
def test_certificate_dataclass_validation(field, value):
    values = dict(
        schema_version=1,
        certificate_id=fp("certificate"),
        chain_id="journal",
        readiness_digest=fp("readiness"),
        retention_plan_digest=fp("retention"),
        compaction_policy_digest=fp("policy"),
        current_sequence=8,
        current_root=fp("current"),
        cutoff_sequence=6,
        cutoff_root=fp("cutoff"),
        archive_id="archive",
        archive_manifest_digest=fp("manifest"),
        protected_roots_digest=fp("protected"),
        issued_at=100.0,
        expires_at=200.0,
    )
    values[field] = value
    with pytest.raises(ValueError):
        DurableCompactionCertificate(
            **values
        )


def test_certificate_rejects_expiry_before_issue():
    with pytest.raises(
        ValueError,
        match="expiry",
    ):
        DurableCompactionCertificate(
            1,
            fp("certificate"),
            "journal",
            fp("readiness"),
            fp("retention"),
            fp("policy"),
            8,
            fp("current"),
            6,
            fp("cutoff"),
            "archive",
            fp("manifest"),
            fp("protected"),
            200.0,
            100.0,
        )


def test_certificate_rejects_cutoff_beyond_current():
    with pytest.raises(
        ValueError,
        match="exceeds",
    ):
        DurableCompactionCertificate(
            1,
            fp("certificate"),
            "journal",
            fp("readiness"),
            fp("retention"),
            fp("policy"),
            5,
            fp("current"),
            6,
            fp("cutoff"),
            "archive",
            fp("manifest"),
            fp("protected"),
            100.0,
            200.0,
        )


def test_signed_certificate_type_validation():
    fixture = Fixture()
    item = fixture.issue()
    with pytest.raises(TypeError):
        SignedDurableCompactionCertificate(
            object(),
            item.signature,
        )
    with pytest.raises(TypeError):
        SignedDurableCompactionCertificate(
            item.certificate,
            object(),
        )


def test_certificate_head_validation():
    with pytest.raises(ValueError):
        DurableCompactionCertificateHead(
            "",
            fp("cert"),
            1,
            fp("root"),
            1.0,
        )
    with pytest.raises(ValueError):
        DurableCompactionCertificateHead(
            "journal",
            "bad",
            1,
            fp("root"),
            1.0,
        )
    with pytest.raises(ValueError):
        DurableCompactionCertificateHead(
            "journal",
            fp("cert"),
            -1,
            fp("root"),
            1.0,
        )


def test_verification_report_serialization():
    fixture = Fixture()
    item = fixture.issue()
    report = fixture.store.inspect(
        item,
        fixture.retention,
        fixture.journal,
    )
    data = report.to_dict()
    assert data["valid"] is True
    assert data["current"] is True
    assert data["expired"] is False
    assert data["allowed"] is True
    assert (
        data["destructive_action_authorized"]
        is False
    )


def test_verification_report_validation():
    with pytest.raises(ValueError):
        DurableCompactionCertificateVerification(
            True,
            True,
            False,
            "bad",
            "journal",
            fp("readiness"),
            fp("current"),
            (),
        )
    with pytest.raises(ValueError):
        DurableCompactionCertificateVerification(
            True,
            True,
            False,
            fp("cert"),
            "",
            fp("readiness"),
            fp("current"),
            (),
        )


def test_certificate_to_dict_declares_non_destructive_authority():
    fixture = Fixture()
    item = fixture.issue()
    data = item.to_dict()
    assert (
        data["destructive_action_authorized"]
        is False
    )
    assert (
        data["certificate"]
        ["destructive_action_authorized"]
        is False
    )
    assert (
        data["certificate"]["authority"]
        == "non-destructive-compaction-readiness"
    )


def test_latest_head_record_matches_current_certificate():
    fixture = Fixture()
    item = fixture.issue()
    record = fixture.backend.get(
        fixture.store.namespace,
        fixture.store._head_key("journal"),
    )
    head = fixture.store._head(
        dict(record.value)
    )
    assert head.certificate_id == item.certificate_id
    assert head.current_sequence == 8
    assert head.current_root == fixture.journal.root_hash()


def test_head_record_tamper_is_rejected():
    fixture = Fixture()
    fixture.issue()
    key = fixture.store._head_key(
        "journal"
    )
    record = fixture.backend.get(
        fixture.store.namespace,
        key,
    )
    raw = dict(record.value)
    raw["chain_id"] = "other"
    fixture.backend.compare_and_swap(
        fixture.store.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    with pytest.raises(
        DurableCompactionCertificateError,
        match="identity",
    ):
        fixture.store.latest(
            "journal"
        )


def test_old_certificate_does_not_become_destructive_when_stale():
    fixture = Fixture()
    item = fixture.issue()
    append_events(
        fixture.journal,
        1,
        start=8,
    )
    report = fixture.store.inspect(
        item,
        fixture.retention,
        fixture.journal,
    )
    assert not report.allowed
    assert not report.destructive_action_authorized
    assert not item.destructive_action_authorized
    assert not item.certificate.destructive_action_authorized
