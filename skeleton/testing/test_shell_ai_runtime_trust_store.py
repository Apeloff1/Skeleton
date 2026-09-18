"""Durable runtime-trust pin store and restart enforcement tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.distributed_state import InMemoryFencedStore
from skeleton.shells.ai.runtime_trust import (
    AIRuntimeTrustGuard,
    RuntimeModelBinding,
    RuntimeTrustEpoch,
    RuntimeTrustSurface,
)
from skeleton.shells.ai.runtime_trust_store import (
    RuntimeTrustPin,
    RuntimeTrustPinConflict,
    RuntimeTrustPinStore,
    SignedRuntimeTrustPin,
)
from skeleton.shells.ai.signed_artifact import ArtifactSigner


def fp(char: str) -> str:
    return char * 64


def surface(**changes) -> RuntimeTrustSurface:
    values = dict(
        code_revision="code-1",
        policy_fingerprint=fp("p"),
        tool_catalog_digest=fp("t"),
        effect_digest=fp("e"),
    )
    values.update(changes)
    return RuntimeTrustSurface(**values)


def epoch(
    *,
    code_revision="code-1",
    model_revision=1,
    model_digest=None,
    release_digest=fp("r"),
    release_id="release-1",
    release_revision=1,
    channel_revision=1,
) -> RuntimeTrustEpoch:
    return RuntimeTrustEpoch(
        1,
        surface(code_revision=code_revision),
        (
            RuntimeModelBinding(
                "provider:model",
                model_revision,
                model_digest or fp("m"),
            ),
        ),
        release_evidence_digest=release_digest,
        release_id=release_id,
        release_revision=release_revision,
        release_channel_revision=channel_revision,
    )


def signer(key=b"k" * 32, key_id="trust-key"):
    return ArtifactSigner(key_id, key)


def store(
    backend=None,
    *,
    item_signer=None,
    namespace="trust-pin",
    clock=lambda: 100.0,
) -> RuntimeTrustPinStore:
    return RuntimeTrustPinStore(
        backend or InMemoryFencedStore(),
        item_signer or signer(),
        namespace=namespace,
        clock=clock,
    )


def test_runtime_trust_pin_initial_pin():
    target = store()
    item = target.pin("production", epoch())
    assert item.pin.scope == "production"
    assert item.pin.revision == 1
    assert item.pin.epoch_digest == epoch().digest
    assert item.pin.previous_pin_digest == ""
    assert item.pin.change_id == ""
    assert item.pin.reason == "startup pin"
    assert item.signature.artifact_type == "ai-runtime-trust-pin"
    assert target.verify("production").ok


def test_runtime_trust_pin_is_idempotent_for_same_epoch():
    target = store()
    first = target.pin("production", epoch())
    second = target.pin(
        "production",
        epoch(),
        reason="another startup",
    )
    assert second == first
    assert target.current("production")[1] == first


def test_runtime_trust_pin_survives_store_restart():
    backend = InMemoryFencedStore()
    first_store = store(backend)
    first = first_store.pin("production", epoch())
    second_store = store(backend)
    current = second_store.current("production")
    assert current is not None
    assert current[1].pin.digest == first.pin.digest
    assert second_store.require(
        "production",
        epoch().digest,
    ).pin.digest == first.pin.digest


def test_runtime_trust_pin_rejects_changed_epoch_without_rollover():
    target = store()
    target.pin("production", epoch())
    changed = epoch(code_revision="code-2")
    with pytest.raises(RuntimeTrustPinConflict, match="differs"):
        target.pin("production", changed)


def test_runtime_trust_require_rejects_wrong_epoch():
    target = store()
    target.pin("production", epoch())
    with pytest.raises(RuntimeTrustPinConflict, match="differs"):
        target.require("production", fp("x"))


def test_runtime_trust_require_requires_existing_scope():
    target = store()
    with pytest.raises(RuntimeTrustPinConflict, match="no durable pin"):
        target.require("production", epoch().digest)


def test_runtime_trust_rollover_happy_path():
    target = store()
    first = target.pin("production", epoch())
    changed = epoch(
        code_revision="code-2",
        release_digest=fp("s"),
        release_id="release-2",
        release_revision=2,
        channel_revision=2,
    )
    second = target.rollover(
        "production",
        changed,
        expected_revision=1,
        change_id="CR-42",
        reason="promote release 2",
    )
    assert second.pin.revision == 2
    assert second.pin.epoch_digest == changed.digest
    assert second.pin.previous_pin_digest == first.pin.digest
    assert second.pin.change_id == "CR-42"
    assert target.require(
        "production",
        changed.digest,
    ) == second
    assert target.verify("production").ok


def test_runtime_trust_rollover_rejects_stale_revision():
    target = store()
    target.pin("production", epoch())
    target.rollover(
        "production",
        epoch(code_revision="code-2"),
        expected_revision=1,
        change_id="CR-1",
        reason="one",
    )
    with pytest.raises(RuntimeTrustPinConflict, match="revision"):
        target.rollover(
            "production",
            epoch(code_revision="code-3"),
            expected_revision=1,
            change_id="CR-2",
            reason="two",
        )


def test_runtime_trust_rollover_requires_existing_scope():
    target = store()
    with pytest.raises(RuntimeTrustPinConflict, match="not pinned"):
        target.rollover(
            "production",
            epoch(code_revision="code-2"),
            expected_revision=1,
            change_id="CR-1",
            reason="one",
        )


def test_runtime_trust_rollover_must_change_epoch():
    target = store()
    target.pin("production", epoch())
    with pytest.raises(RuntimeTrustPinConflict, match="does not change"):
        target.rollover(
            "production",
            epoch(),
            expected_revision=1,
            change_id="CR-1",
            reason="same",
        )


@pytest.mark.parametrize(
    "change_id,reason",
    [
        ("", "reason"),
        ("CR-1", ""),
    ],
)
def test_runtime_trust_rollover_requires_change_evidence(change_id, reason):
    target = store()
    target.pin("production", epoch())
    with pytest.raises(ValueError):
        target.rollover(
            "production",
            epoch(code_revision="code-2"),
            expected_revision=1,
            change_id=change_id,
            reason=reason,
        )


def test_runtime_trust_rollover_revision_capacity():
    target = RuntimeTrustPinStore(
        InMemoryFencedStore(),
        signer(),
        namespace="trust",
        max_revisions=1,
        clock=lambda: 1.0,
    )
    target.pin("production", epoch())
    with pytest.raises(RuntimeError, match="capacity"):
        target.rollover(
            "production",
            epoch(code_revision="code-2"),
            expected_revision=1,
            change_id="CR-1",
            reason="roll",
        )


def test_runtime_trust_history_items_are_signed():
    target = store()
    first = target.pin("production", epoch())
    second = target.rollover(
        "production",
        epoch(code_revision="code-2"),
        expected_revision=1,
        change_id="CR-1",
        reason="roll",
    )
    assert target.history_item("production", 1) == first
    assert target.history_item("production", 2) == second


def test_runtime_trust_history_missing_revision_fails_verify():
    backend = InMemoryFencedStore()
    target = store(backend)
    target.pin("production", epoch())
    target.rollover(
        "production",
        epoch(code_revision="code-2"),
        expected_revision=1,
        change_id="CR-1",
        reason="roll",
    )
    record = backend.get(
        target.namespace,
        target._history_key("production", 1),
    )
    assert record is not None
    backend.delete(
        target.namespace,
        target._history_key("production", 1),
        expected_revision=record.revision,
    )
    report = target.verify("production")
    assert not report.ok
    assert any("history 1" in reason for reason in report.reasons)


def test_runtime_trust_history_predecessor_tamper_fails_verify():
    backend = InMemoryFencedStore()
    target = store(backend)
    target.pin("production", epoch())
    target.rollover(
        "production",
        epoch(code_revision="code-2"),
        expected_revision=1,
        change_id="CR-1",
        reason="roll",
    )
    record = backend.get(
        target.namespace,
        target._history_key("production", 2),
    )
    item = target._decode(record.value)
    tampered_pin = replace(
        item.pin,
        previous_pin_digest=fp("x"),
    )
    tampered = SignedRuntimeTrustPin(
        tampered_pin,
        signer().sign(
            "ai-runtime-trust-pin",
            tampered_pin.digest,
            metadata={
                "scope": tampered_pin.scope,
                "revision": str(tampered_pin.revision),
            },
        ),
    )
    backend.compare_and_swap(
        target.namespace,
        target._history_key("production", 2),
        expected_revision=record.revision,
        value=tampered.to_dict(),
    )
    report = target.verify("production")
    assert not report.ok
    assert any("predecessor" in reason for reason in report.reasons)


def test_runtime_trust_wrong_signing_key_rejects_current():
    backend = InMemoryFencedStore()
    first = store(backend)
    first.pin("production", epoch())
    second = store(
        backend,
        item_signer=signer(b"x" * 32),
    )
    with pytest.raises(RuntimeTrustPinConflict, match="signature"):
        second.current("production")


def test_runtime_trust_wrong_key_id_rejects_current():
    backend = InMemoryFencedStore()
    first = store(backend)
    first.pin("production", epoch())
    second = store(
        backend,
        item_signer=signer(key_id="other"),
    )
    with pytest.raises(RuntimeTrustPinConflict, match="signature"):
        second.current("production")


def test_runtime_trust_head_tamper_rejects_current():
    backend = InMemoryFencedStore()
    target = store(backend)
    target.pin("production", epoch())
    key = target._head_key("production")
    record = backend.get(target.namespace, key)
    raw = dict(record.value)
    raw_pin = dict(raw["pin"])
    raw_pin["epoch_digest"] = fp("x")
    raw["pin"] = raw_pin
    backend.compare_and_swap(
        target.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    with pytest.raises(
        (RuntimeTrustPinConflict, ValueError),
    ):
        target.current("production")


def test_runtime_trust_signature_metadata_scope_is_verified():
    backend = InMemoryFencedStore()
    target = store(backend)
    item = target.pin("production", epoch())
    key = target._head_key("production")
    record = backend.get(target.namespace, key)
    raw = dict(record.value)
    raw_sig = dict(raw["signature"])
    raw_sig["metadata"] = {
        "scope": "other",
        "revision": "1",
    }
    raw["signature"] = raw_sig
    backend.compare_and_swap(
        target.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    with pytest.raises(RuntimeTrustPinConflict, match="scope"):
        target.current("production")


def test_runtime_trust_signature_metadata_revision_is_verified():
    backend = InMemoryFencedStore()
    target = store(backend)
    target.pin("production", epoch())
    key = target._head_key("production")
    record = backend.get(target.namespace, key)
    raw = dict(record.value)
    raw_sig = dict(raw["signature"])
    raw_sig["metadata"] = {
        "scope": "production",
        "revision": "2",
    }
    raw["signature"] = raw_sig
    backend.compare_and_swap(
        target.namespace,
        key,
        expected_revision=record.revision,
        value=raw,
    )
    with pytest.raises(RuntimeTrustPinConflict, match="revision"):
        target.current("production")


@pytest.mark.parametrize(
    "scope",
    ["", " space", "bad?scope", "x" * 129],
)
def test_runtime_trust_scope_validation(scope):
    target = store()
    with pytest.raises(ValueError, match="scope"):
        target.pin(scope, epoch())


def test_runtime_trust_pin_dataclass_validation():
    with pytest.raises(ValueError, match="schema"):
        RuntimeTrustPin(
            2,
            "production",
            1,
            fp("e"),
        )
    with pytest.raises(ValueError, match="revision"):
        RuntimeTrustPin(
            1,
            "production",
            0,
            fp("e"),
        )
    with pytest.raises(ValueError, match="epoch"):
        RuntimeTrustPin(
            1,
            "production",
            1,
            "bad",
        )


def test_runtime_trust_first_pin_rejects_predecessor():
    with pytest.raises(ValueError, match="first"):
        RuntimeTrustPin(
            1,
            "production",
            1,
            fp("e"),
            fp("p"),
        )


def test_runtime_trust_later_pin_requires_predecessor_and_change_id():
    with pytest.raises(ValueError, match="predecessor"):
        RuntimeTrustPin(
            1,
            "production",
            2,
            fp("e"),
        )
    with pytest.raises(ValueError, match="change_id"):
        RuntimeTrustPin(
            1,
            "production",
            2,
            fp("e"),
            fp("p"),
        )


def test_signed_runtime_trust_pin_rejects_wrong_artifact_type():
    pin = RuntimeTrustPin(
        1,
        "production",
        1,
        fp("e"),
        pinned_at=1,
    )
    signature = signer().sign(
        "other",
        pin.digest,
    )
    with pytest.raises(ValueError, match="artifact"):
        SignedRuntimeTrustPin(pin, signature)


def test_signed_runtime_trust_pin_rejects_wrong_digest():
    pin = RuntimeTrustPin(
        1,
        "production",
        1,
        fp("e"),
        pinned_at=1,
    )
    signature = signer().sign(
        "ai-runtime-trust-pin",
        fp("x"),
    )
    with pytest.raises(ValueError, match="digest"):
        SignedRuntimeTrustPin(pin, signature)


def test_runtime_trust_guard_durable_store_initial_pin():
    backend = InMemoryFencedStore()
    durable = store(backend)
    guard = AIRuntimeTrustGuard(
        surface(),
        durable_store=durable,
        durable_scope="production",
    )
    report = guard.pin()
    assert report.allowed
    current = durable.current("production")
    assert current[1].pin.epoch_digest == report.epoch_digest


def test_runtime_trust_guard_restart_reuses_durable_pin():
    backend = InMemoryFencedStore()
    durable = store(backend)
    first = AIRuntimeTrustGuard(
        surface(),
        durable_store=durable,
        durable_scope="production",
    )
    pinned = first.pin()
    second = AIRuntimeTrustGuard(
        surface(),
        durable_store=store(backend),
        durable_scope="production",
    )
    restarted = second.pin()
    assert restarted.epoch_digest == pinned.epoch_digest
    assert second.require_current().allowed


def test_runtime_trust_guard_restart_rejects_changed_surface():
    backend = InMemoryFencedStore()
    durable = store(backend)
    AIRuntimeTrustGuard(
        surface(),
        durable_store=durable,
        durable_scope="production",
    ).pin()
    changed = AIRuntimeTrustGuard(
        surface(code_revision="code-2"),
        durable_store=store(backend),
        durable_scope="production",
    )
    with pytest.raises(RuntimeError, match="differs"):
        changed.pin()


def test_runtime_trust_guard_requires_durable_pin_on_current_check():
    backend = InMemoryFencedStore()
    durable = store(backend)
    guard = AIRuntimeTrustGuard(
        surface(),
        durable_store=durable,
        durable_scope="production",
    )
    guard.pin()
    head = backend.get(
        durable.namespace,
        durable._head_key("production"),
    )
    backend.delete(
        durable.namespace,
        durable._head_key("production"),
        expected_revision=head.revision,
    )
    with pytest.raises(RuntimeError, match="no durable pin"):
        guard.require_current()


def test_runtime_trust_guard_durable_configuration_is_paired():
    with pytest.raises(ValueError, match="configured together"):
        AIRuntimeTrustGuard(
            surface(),
            durable_store=store(),
        )
    with pytest.raises(ValueError, match="configured together"):
        AIRuntimeTrustGuard(
            surface(),
            durable_scope="production",
        )


def test_runtime_trust_guard_durable_scope_limit():
    with pytest.raises(ValueError, match="scope"):
        AIRuntimeTrustGuard(
            surface(),
            durable_store=store(),
            durable_scope="x" * 129,
        )


def test_runtime_trust_explicit_rollover_allows_new_restart_epoch():
    backend = InMemoryFencedStore()
    durable = store(backend)
    first_guard = AIRuntimeTrustGuard(
        surface(),
        durable_store=durable,
        durable_scope="production",
    )
    first = first_guard.pin()

    new_epoch = RuntimeTrustEpoch(
        1,
        surface(code_revision="code-2"),
    )
    durable.rollover(
        "production",
        new_epoch,
        expected_revision=1,
        change_id="CR-99",
        reason="approved deployment",
    )
    restarted = AIRuntimeTrustGuard(
        surface(code_revision="code-2"),
        durable_store=store(backend),
        durable_scope="production",
    )
    report = restarted.pin()
    assert report.epoch_digest == new_epoch.digest
    assert report.epoch_digest != first.epoch_digest


def test_runtime_trust_old_worker_detects_durable_rollover():
    backend = InMemoryFencedStore()
    durable = store(backend)
    guard = AIRuntimeTrustGuard(
        surface(),
        durable_store=durable,
        durable_scope="production",
    )
    first = guard.pin()
    new_epoch = RuntimeTrustEpoch(
        1,
        surface(code_revision="code-2"),
    )
    durable.rollover(
        "production",
        new_epoch,
        expected_revision=1,
        change_id="CR-99",
        reason="approved deployment",
    )
    with pytest.raises(RuntimeError, match="differs"):
        guard.require_current()


def test_runtime_trust_store_verify_empty_scope_is_ok():
    report = store().verify("production")
    assert report.ok
    assert report.revision == 0
    assert report.epoch_digest == ""


def test_runtime_trust_store_verification_reports_current_epoch():
    target = store()
    item = target.pin("production", epoch())
    report = target.verify("production")
    assert report.ok
    assert report.revision == 1
    assert report.epoch_digest == epoch().digest
    assert report.pin_digest == item.pin.digest


def test_runtime_trust_store_to_dict_shapes_are_json_ready():
    target = store()
    item = target.pin("production", epoch())
    assert item.to_dict()["pin"]["scope"] == "production"
    report = target.verify("production").to_dict()
    assert report["ok"] is True
    assert report["revision"] == 1
