"""Signed durable recovery requirement manifest tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.recovery_requirements import (
    DurableRecoveryRequirementConflict,
    DurableRecoveryRequirementManifest,
    DurableRecoveryRequirementStore,
    DurableRecoveryRequirementVerification,
    SignedDurableRecoveryRequirementManifest,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner, SignedArtifact


def fp(char: str) -> str:
    return char * 64


def store(
    backend=None,
    *,
    namespace="requirements",
    clock=lambda: 10.0,
    max_finalizations=4096,
    max_generations=10000,
    max_retries=16,
):
    backend = backend or InMemoryFencedStore()
    return DurableRecoveryRequirementStore(
        backend,
        ArtifactSigner(
            "requirements-key",
            b"k" * 32,
            clock=clock,
        ),
        namespace=namespace,
        max_finalizations=max_finalizations,
        max_generations=max_generations,
        max_retries=max_retries,
        clock=clock,
    )


def test_initialize_sorts_and_signs_required_ids():
    requirements = store()
    item = requirements.initialize(
        "prod",
        ("finalization-b", "finalization-a"),
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
    )
    manifest = item.manifest
    assert manifest.generation == 1
    assert manifest.finalization_ids == (
        "finalization-a",
        "finalization-b",
    )
    assert manifest.previous_manifest_digest == ""
    assert manifest.runtime_trust_digest == fp("t")
    assert manifest.release_evidence_digest == fp("r")
    assert item.signature.artifact_type == "ai-durable-recovery-requirements"
    assert item.signature.artifact_digest == manifest.digest
    assert item.signature.metadata["scope"] == "prod"
    assert item.signature.metadata["generation"] == "1"


def test_initialize_is_idempotent_for_same_authority():
    requirements = store()
    first = requirements.initialize(
        "prod",
        ("a", "b"),
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
    )
    second = requirements.initialize(
        "prod",
        ("b", "a"),
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
    )
    assert second == first
    assert requirements.current("prod")[0] == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"finalization_ids": ("different",)},
        {"runtime_trust_digest": fp("x")},
        {"release_evidence_digest": fp("x")},
    ],
)
def test_initialize_rejects_different_existing_authority(changes):
    requirements = store()
    requirements.initialize(
        "prod",
        ("a",),
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
    )
    values = {
        "finalization_ids": ("a",),
        "runtime_trust_digest": fp("t"),
        "release_evidence_digest": fp("r"),
    }
    values.update(changes)
    with pytest.raises(
        DurableRecoveryRequirementConflict,
        match="initialized differently",
    ):
        requirements.initialize(
            "prod",
            values["finalization_ids"],
            runtime_trust_digest=values["runtime_trust_digest"],
            release_evidence_digest=values["release_evidence_digest"],
        )


def test_rollover_links_predecessor_and_advances_generation():
    requirements = store()
    first = requirements.initialize("prod", ("a",))
    second = requirements.rollover(
        "prod",
        ("a", "b"),
        expected_generation=1,
        change_id="chg-1",
        reason="add b after terminal execution",
    )
    assert second.manifest.generation == 2
    assert second.manifest.previous_manifest_digest == first.manifest.digest
    assert second.manifest.change_id == "chg-1"
    assert second.manifest.finalization_ids == ("a", "b")
    assert requirements.current("prod")[0] == 2


def test_rollover_preserves_runtime_and_release_bindings_by_default():
    requirements = store()
    requirements.initialize(
        "prod",
        ("a",),
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
    )
    second = requirements.rollover(
        "prod",
        ("a", "b"),
        expected_generation=1,
        change_id="chg",
        reason="add b",
    )
    assert second.manifest.runtime_trust_digest == fp("t")
    assert second.manifest.release_evidence_digest == fp("r")


def test_rollover_can_explicitly_change_runtime_and_release_bindings():
    requirements = store()
    requirements.initialize(
        "prod",
        ("a",),
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
    )
    second = requirements.rollover(
        "prod",
        ("a",),
        expected_generation=1,
        change_id="trust-roll",
        reason="approved runtime and release migration",
        runtime_trust_digest=fp("u"),
        release_evidence_digest=fp("s"),
    )
    assert second.manifest.runtime_trust_digest == fp("u")
    assert second.manifest.release_evidence_digest == fp("s")


def test_rollover_rejects_noop_authority_change():
    requirements = store()
    requirements.initialize("prod", ("a",))
    with pytest.raises(
        DurableRecoveryRequirementConflict,
        match="no authority change",
    ):
        requirements.rollover(
            "prod",
            ("a",),
            expected_generation=1,
            change_id="noop",
            reason="noop",
        )


def test_rollover_rejects_stale_generation():
    requirements = store()
    requirements.initialize("prod", ("a",))
    requirements.rollover(
        "prod",
        ("a", "b"),
        expected_generation=1,
        change_id="first",
        reason="first",
    )
    with pytest.raises(
        DurableRecoveryRequirementConflict,
        match="generation conflict",
    ):
        requirements.rollover(
            "prod",
            ("a", "b", "c"),
            expected_generation=1,
            change_id="stale",
            reason="stale",
        )


def test_add_merges_without_duplicates():
    requirements = store()
    requirements.initialize("prod", ("a", "b"))
    item = requirements.add(
        "prod",
        ("b", "c"),
        expected_generation=1,
        change_id="add-c",
        reason="terminal execution c",
    )
    assert item.manifest.finalization_ids == ("a", "b", "c")


def test_remove_requires_explicit_change_and_preserves_remaining():
    requirements = store()
    requirements.initialize("prod", ("a", "b", "c"))
    item = requirements.remove(
        "prod",
        ("b",),
        expected_generation=1,
        change_id="retire-b",
        reason="b exceeded retention and has external archive",
    )
    assert item.manifest.finalization_ids == ("a", "c")
    assert item.manifest.generation == 2


def test_remove_unknown_finalization_is_rejected():
    requirements = store()
    requirements.initialize("prod", ("a",))
    with pytest.raises(
        DurableRecoveryRequirementConflict,
        match="not in required set",
    ):
        requirements.remove(
            "prod",
            ("missing",),
            expected_generation=1,
            change_id="bad",
            reason="bad",
        )


def test_verify_history_accepts_intact_chain():
    requirements = store()
    first = requirements.initialize(
        "prod",
        ("a",),
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
    )
    second = requirements.add(
        "prod",
        ("b",),
        expected_generation=1,
        change_id="add-b",
        reason="add b",
    )
    third = requirements.remove(
        "prod",
        ("a",),
        expected_generation=2,
        change_id="remove-a",
        reason="archive a",
    )
    report = requirements.verify_history(
        "prod",
        runtime_trust_digest=fp("t"),
        release_evidence_digest=fp("r"),
    )
    assert report.ok
    assert report.generation == 3
    assert report.manifest_digest == third.manifest.digest
    assert report.finalization_ids == ("b",)
    assert requirements.history_item("prod", 1) == first
    assert requirements.history_item("prod", 2) == second


def test_require_returns_current_only_after_full_history_verification():
    requirements = store()
    requirements.initialize("prod", ("a",))
    current = requirements.require("prod")
    assert current.manifest.finalization_ids == ("a",)


def test_verify_history_detects_runtime_binding_drift():
    requirements = store()
    requirements.initialize(
        "prod",
        ("a",),
        runtime_trust_digest=fp("t"),
    )
    report = requirements.verify_history(
        "prod",
        runtime_trust_digest=fp("x"),
    )
    assert not report.ok
    assert "runtime trust" in report.reasons[-1]


def test_verify_history_detects_release_binding_drift():
    requirements = store()
    requirements.initialize(
        "prod",
        ("a",),
        release_evidence_digest=fp("r"),
    )
    report = requirements.verify_history(
        "prod",
        release_evidence_digest=fp("x"),
    )
    assert not report.ok
    assert "release binding" in report.reasons[-1]


def test_unbound_runtime_or_release_can_be_verified_without_expectation():
    requirements = store()
    requirements.initialize("prod", ("a",))
    assert requirements.verify_history("prod").ok


def test_missing_scope_is_reported_not_raised_by_verify_history():
    requirements = store()
    report = requirements.verify_history("missing")
    assert not report.ok
    assert report.generation == 0
    assert report.finalization_ids == ()
    assert report.reasons == (
        "recovery requirement scope has no manifest",
    )


def test_require_missing_scope_raises():
    requirements = store()
    with pytest.raises(
        DurableRecoveryRequirementConflict,
        match="no manifest",
    ):
        requirements.require("missing")


def test_history_signature_tamper_is_detected():
    backend = InMemoryFencedStore()
    requirements = store(backend)
    item = requirements.initialize("prod", ("a",))
    key = requirements._history_key("prod", 1)
    record = backend.get(requirements.namespace, key)
    raw = dict(record.value)
    signature = dict(raw["signature"])
    signature["signature"] = "0" * 64
    raw["signature"] = signature
    backend.compare_and_swap(
        requirements.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    with pytest.raises(
        DurableRecoveryRequirementConflict,
        match="signature",
    ):
        requirements.history_item("prod", 1)
    assert item.manifest.finalization_ids == ("a",)


def test_head_signature_tamper_is_detected():
    backend = InMemoryFencedStore()
    requirements = store(backend)
    requirements.initialize("prod", ("a",))
    key = requirements._head_key("prod")
    record = backend.get(requirements.namespace, key)
    raw = dict(record.value)
    signature = dict(raw["signature"])
    signature["signature"] = "f" * 64
    raw["signature"] = signature
    backend.compare_and_swap(
        requirements.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    with pytest.raises(
        DurableRecoveryRequirementConflict,
        match="signature",
    ):
        requirements.current("prod")


def test_head_rollback_to_old_signed_manifest_is_detected_by_revision():
    backend = InMemoryFencedStore()
    requirements = store(backend)
    first = requirements.initialize("prod", ("a",))
    requirements.add(
        "prod",
        ("b",),
        expected_generation=1,
        change_id="add-b",
        reason="add b",
    )
    key = requirements._head_key("prod")
    record = backend.get(requirements.namespace, key)
    backend.compare_and_swap(
        requirements.namespace,
        key,
        expected_revision=record.revision,
        value=first.to_dict(),
    )
    with pytest.raises(
        DurableRecoveryRequirementConflict,
        match="generation/revision mismatch",
    ):
        requirements.current("prod")


def test_history_predecessor_substitution_is_detected():
    backend = InMemoryFencedStore()
    requirements = store(backend)
    requirements.initialize("prod", ("a",))
    second = requirements.add(
        "prod",
        ("b",),
        expected_generation=1,
        change_id="add-b",
        reason="add b",
    )
    key = requirements._history_key("prod", 2)
    record = backend.get(requirements.namespace, key)
    forged_manifest = replace(
        second.manifest,
        previous_manifest_digest=fp("x"),
    )
    forged = requirements._sign(forged_manifest)
    backend.compare_and_swap(
        requirements.namespace,
        key,
        expected_revision=record.revision,
        value=forged.to_dict(),
    )
    report = requirements.verify_history("prod")
    assert not report.ok
    assert any(
        "predecessor mismatch" in reason
        for reason in report.reasons
    )


def test_head_not_terminal_history_generation_is_detected():
    backend = InMemoryFencedStore()
    requirements = store(backend)
    requirements.initialize("prod", ("a",))
    second = requirements.add(
        "prod",
        ("b",),
        expected_generation=1,
        change_id="add-b",
        reason="add b",
    )
    history_key = requirements._history_key("prod", 2)
    record = backend.get(requirements.namespace, history_key)
    raw = dict(record.value)
    manifest_raw = dict(raw["manifest"])
    manifest_raw["finalization_ids"] = ["a", "different"]
    forged_manifest = DurableRecoveryRequirementManifest(
        int(manifest_raw["schema_version"]),
        str(manifest_raw["scope"]),
        int(manifest_raw["generation"]),
        tuple(manifest_raw["finalization_ids"]),
        str(manifest_raw["previous_manifest_digest"]),
        str(manifest_raw["runtime_trust_digest"]),
        str(manifest_raw["release_evidence_digest"]),
        str(manifest_raw["change_id"]),
        str(manifest_raw["reason"]),
        float(manifest_raw["created_at"]),
    )
    forged_history = requirements._sign(forged_manifest)
    backend.compare_and_swap(
        requirements.namespace,
        history_key,
        expected_revision=record.revision,
        value=forged_history.to_dict(),
    )
    report = requirements.verify_history("prod")
    assert not report.ok
    assert second.manifest.digest != forged_manifest.digest


def test_fresh_reader_verifies_existing_history():
    backend = InMemoryFencedStore()
    writer = store(backend, namespace="requirements")
    writer.initialize("prod", ("a",))
    writer.add(
        "prod",
        ("b",),
        expected_generation=1,
        change_id="add-b",
        reason="add b",
    )
    reader = store(backend, namespace="requirements")
    report = reader.verify_history("prod")
    assert report.ok
    assert report.generation == 2
    assert report.finalization_ids == ("a", "b")


def test_namespaces_isolate_scopes_and_stores():
    backend = InMemoryFencedStore()
    one = store(backend, namespace="one")
    two = store(backend, namespace="two")
    one.initialize("prod", ("a",))
    two.initialize("prod", ("b",))
    assert one.require("prod").manifest.finalization_ids == ("a",)
    assert two.require("prod").manifest.finalization_ids == ("b",)


def test_scopes_are_independent_within_store():
    requirements = store()
    requirements.initialize("prod", ("a",))
    requirements.initialize("staging", ("b",))
    assert requirements.require("prod").manifest.finalization_ids == ("a",)
    assert requirements.require("staging").manifest.finalization_ids == ("b",)


@pytest.mark.parametrize(
    "scope",
    ["", " space", "x" * 129, "bad?scope"],
)
def test_scope_validation(scope):
    requirements = store()
    with pytest.raises(ValueError, match="scope"):
        requirements.initialize(scope, ())


@pytest.mark.parametrize(
    "ids",
    [
        ("",),
        ("x" * 257,),
        ("dup", "dup"),
    ],
)
def test_finalization_id_validation(ids):
    requirements = store()
    with pytest.raises(ValueError):
        requirements.initialize("prod", ids)


def test_finalization_bound_is_enforced():
    requirements = store(max_finalizations=2)
    with pytest.raises(ValueError, match="bound"):
        requirements.initialize(
            "prod",
            ("a", "b", "c"),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_finalizations": 0},
        {"max_generations": 0},
        {"max_retries": 0},
        {"max_finalizations": True},
        {"max_generations": True},
        {"max_retries": True},
    ],
)
def test_store_positive_integer_validation(kwargs):
    with pytest.raises(ValueError):
        store(**kwargs)


def test_store_hard_finalization_bound():
    with pytest.raises(ValueError, match="hard bound"):
        store(max_finalizations=4097)


def test_store_hard_retry_bound():
    with pytest.raises(ValueError, match="hard bound"):
        store(max_retries=65)


def test_generation_capacity_exhaustion():
    requirements = store(max_generations=1)
    requirements.initialize("prod", ("a",))
    with pytest.raises(RuntimeError, match="capacity"):
        requirements.add(
            "prod",
            ("b",),
            expected_generation=1,
            change_id="add-b",
            reason="add b",
        )


@pytest.mark.parametrize(
    "expected_generation",
    [0, -1, True, 1.5],
)
def test_rollover_expected_generation_validation(expected_generation):
    requirements = store()
    requirements.initialize("prod", ("a",))
    with pytest.raises(ValueError, match="expected_generation"):
        requirements.rollover(
            "prod",
            ("a", "b"),
            expected_generation=expected_generation,
            change_id="change",
            reason="change",
        )


def test_rollover_requires_change_id():
    requirements = store()
    requirements.initialize("prod", ("a",))
    with pytest.raises(ValueError, match="change_id"):
        requirements.rollover(
            "prod",
            ("a", "b"),
            expected_generation=1,
            change_id="",
            reason="change",
        )


def test_rollover_requires_reason():
    requirements = store()
    requirements.initialize("prod", ("a",))
    with pytest.raises(ValueError, match="reason"):
        requirements.rollover(
            "prod",
            ("a", "b"),
            expected_generation=1,
            change_id="change",
            reason="",
        )


def test_manifest_digest_is_deterministic():
    one = DurableRecoveryRequirementManifest(
        1,
        "prod",
        1,
        ("b", "a"),
        "",
        fp("t"),
        fp("r"),
        "",
        "initial",
        10.0,
    )
    two = DurableRecoveryRequirementManifest(
        1,
        "prod",
        1,
        ("a", "b"),
        "",
        fp("t"),
        fp("r"),
        "",
        "initial",
        10.0,
    )
    assert one == two
    assert one.digest == two.digest


def test_manifest_digest_changes_for_required_set():
    one = DurableRecoveryRequirementManifest(
        1, "prod", 1, ("a",), reason="initial", created_at=10.0
    )
    two = DurableRecoveryRequirementManifest(
        1, "prod", 1, ("b",), reason="initial", created_at=10.0
    )
    assert one.digest != two.digest


def test_manifest_to_dict_is_json_shaped():
    manifest = DurableRecoveryRequirementManifest(
        1,
        "prod",
        1,
        ("a",),
        "",
        fp("t"),
        fp("r"),
        "",
        "initial",
        10.0,
    )
    data = manifest.to_dict()
    assert data["scope"] == "prod"
    assert data["generation"] == 1
    assert data["finalization_ids"] == ["a"]
    assert data["runtime_trust_digest"] == fp("t")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"schema_version": 2},
        {"generation": 0},
        {"created_at": -1.0},
        {"created_at": float("inf")},
    ],
)
def test_manifest_validation(kwargs):
    values = dict(
        schema_version=1,
        scope="prod",
        generation=1,
        finalization_ids=("a",),
        reason="initial",
        created_at=10.0,
    )
    values.update(kwargs)
    with pytest.raises(ValueError):
        DurableRecoveryRequirementManifest(**values)


def test_rollover_manifest_requires_predecessor():
    with pytest.raises(ValueError, match="predecessor"):
        DurableRecoveryRequirementManifest(
            1,
            "prod",
            2,
            ("a",),
            "",
            "",
            "",
            "change",
            "reason",
            10.0,
        )


def test_initial_manifest_rejects_predecessor():
    with pytest.raises(ValueError, match="initial"):
        DurableRecoveryRequirementManifest(
            1,
            "prod",
            1,
            ("a",),
            fp("p"),
            "",
            "",
            "",
            "initial",
            10.0,
        )


def test_signed_manifest_rejects_wrong_artifact_type():
    manifest = DurableRecoveryRequirementManifest(
        1,
        "prod",
        1,
        (),
        reason="initial",
        created_at=10.0,
    )
    signature = SignedArtifact(
        "wrong",
        manifest.digest,
        "key",
        10.0,
        {},
        "0" * 64,
    )
    with pytest.raises(ValueError, match="artifact type"):
        SignedDurableRecoveryRequirementManifest(
            manifest,
            signature,
        )


def test_signed_manifest_rejects_wrong_digest():
    manifest = DurableRecoveryRequirementManifest(
        1,
        "prod",
        1,
        (),
        reason="initial",
        created_at=10.0,
    )
    signature = SignedArtifact(
        "ai-durable-recovery-requirements",
        fp("x"),
        "key",
        10.0,
        {},
        "0" * 64,
    )
    with pytest.raises(ValueError, match="digest"):
        SignedDurableRecoveryRequirementManifest(
            manifest,
            signature,
        )


def test_verification_to_dict():
    report = DurableRecoveryRequirementVerification(
        True,
        "prod",
        2,
        fp("a"),
        ("b", "a"),
        (),
    )
    assert report.to_dict() == {
        "ok": True,
        "scope": "prod",
        "generation": 2,
        "manifest_digest": fp("a"),
        "finalization_ids": ["a", "b"],
        "reasons": [],
    }


def test_runtime_binding_can_be_cleared_explicitly():
    requirements = store()
    requirements.initialize(
        "prod",
        ("a",),
        runtime_trust_digest=fp("t"),
    )
    item = requirements.rollover(
        "prod",
        ("a",),
        expected_generation=1,
        change_id="clear-runtime",
        reason="runtime binding intentionally retired",
        runtime_trust_digest="",
    )
    assert item.manifest.runtime_trust_digest == ""


def test_release_binding_can_be_cleared_explicitly():
    requirements = store()
    requirements.initialize(
        "prod",
        ("a",),
        release_evidence_digest=fp("r"),
    )
    item = requirements.rollover(
        "prod",
        ("a",),
        expected_generation=1,
        change_id="clear-release",
        reason="release binding intentionally retired",
        release_evidence_digest="",
    )
    assert item.manifest.release_evidence_digest == ""


def test_remove_last_requirement_produces_explicit_empty_generation():
    requirements = store()
    requirements.initialize("prod", ("a",))
    item = requirements.remove(
        "prod",
        ("a",),
        expected_generation=1,
        change_id="archive-last",
        reason="archived final proof",
    )
    assert item.manifest.finalization_ids == ()
    assert item.manifest.generation == 2
    assert requirements.verify_history("prod").ok


def test_history_items_are_immutable_by_generation():
    requirements = store()
    first = requirements.initialize("prod", ("a",))
    requirements.add(
        "prod",
        ("b",),
        expected_generation=1,
        change_id="add-b",
        reason="add b",
    )
    reloaded = requirements.history_item("prod", 1)
    assert reloaded.manifest.digest == first.manifest.digest
    assert reloaded.manifest.finalization_ids == ("a",)
