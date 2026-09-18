"""Context provenance, execution preconditions, seals, and replay tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from skeleton.shells.ai.context_policy import ContextPolicy, ContextPolicyEngine
from skeleton.shells.ai.context_provenance import (
    ContextBundle,
    ContextItem,
    ContextKind,
    ContextSensitivity,
    ContextTrust,
)
from skeleton.shells.ai.execution_seal import (
    ExecutionSealAuthority,
    ExecutionSealError,
)
from skeleton.shells.ai.preconditions import (
    Preconditions,
    PreconditionChecker,
    ResourcePrecondition,
)
from skeleton.shells.ai.seal_registry import ExecutionSealRegistry, SealReplay
from skeleton.shells.ai.stale_guard import PlanPin


def fp(char):
    return char * 64


def item(
    item_id="x",
    *,
    content="hello",
    trust=ContextTrust.TRUSTED,
    sensitivity=ContextSensitivity.INTERNAL,
):
    return ContextItem(
        item_id,
        ContextKind.REPOSITORY,
        trust,
        sensitivity,
        content,
        "repo",
    )


def pin():
    return PlanPin(
        fp("a"),
        fp("b"),
        fp("c"),
        fp("d"),
        fp("e"),
        fp("f"),
        fp("1"),
    )


def test_context_item_digest_not_content_in_redacted_dict():
    value = item(content="private-ish")
    data = value.to_dict(include_content=False)
    assert "content" not in data
    assert len(data["content_digest"]) == 64


def test_context_bundle_digest_stable():
    bundle = ContextBundle((item(),))
    assert bundle.digest == bundle.digest
    assert len(bundle.digest) == 64


def test_context_bundle_duplicate_ids_rejected():
    with pytest.raises(ValueError):
        ContextBundle((item("a"), item("a")))


def test_context_bundle_byte_budget():
    with pytest.raises(ValueError):
        ContextBundle((item(content="abcdef"),), max_total_bytes=5)


def test_context_secret_items_identified():
    secret = item(
        "s",
        sensitivity=ContextSensitivity.SECRET,
    )
    bundle = ContextBundle((secret,))
    assert bundle.secret_items == (secret,)


def test_context_untrusted_items_identified():
    untrusted = item("u", trust=ContextTrust.UNTRUSTED)
    bundle = ContextBundle((untrusted,))
    assert bundle.untrusted_items == (untrusted,)


def test_context_model_safe_drops_secret():
    secret = item("s", sensitivity=ContextSensitivity.SECRET)
    public = item("p", sensitivity=ContextSensitivity.PUBLIC)
    safe = ContextBundle((secret, public)).model_safe()
    assert safe.items == (public,)


def test_context_payload_rejects_secret():
    bundle = ContextBundle(
        (item("s", sensitivity=ContextSensitivity.SECRET),)
    )
    with pytest.raises(ValueError):
        bundle.to_model_payload()


def test_context_policy_allows_internal_trusted():
    bundle = ContextBundle((item(),))
    decision = ContextPolicyEngine().inspect(bundle)
    assert decision.allowed


def test_context_policy_denies_secret():
    bundle = ContextBundle(
        (item("s", sensitivity=ContextSensitivity.SECRET),)
    )
    decision = ContextPolicyEngine().inspect(bundle)
    assert not decision.allowed
    assert any("secret" in reason for reason in decision.reasons)


def test_context_policy_denies_confidential_by_default():
    bundle = ContextBundle(
        (item("c", sensitivity=ContextSensitivity.CONFIDENTIAL),)
    )
    assert not ContextPolicyEngine().inspect(bundle).allowed


def test_context_policy_can_allow_confidential():
    bundle = ContextBundle(
        (item("c", sensitivity=ContextSensitivity.CONFIDENTIAL),)
    )
    engine = ContextPolicyEngine(ContextPolicy(allow_confidential=True))
    assert engine.inspect(bundle).allowed


def test_context_policy_can_deny_untrusted():
    bundle = ContextBundle(
        (item("u", trust=ContextTrust.UNTRUSTED),)
    )
    engine = ContextPolicyEngine(ContextPolicy(allow_untrusted=False))
    assert not engine.inspect(bundle).allowed


def test_context_policy_untrusted_byte_budget():
    bundle = ContextBundle(
        (item("u", content="abcdef", trust=ContextTrust.UNTRUSTED),)
    )
    engine = ContextPolicyEngine(ContextPolicy(max_untrusted_bytes=5))
    assert not engine.inspect(bundle).allowed


def test_context_policy_require_raises():
    bundle = ContextBundle(
        (item("s", sensitivity=ContextSensitivity.SECRET),)
    )
    with pytest.raises(PermissionError):
        ContextPolicyEngine().require(bundle)


def test_preconditions_digest_stable():
    conditions = Preconditions(
        (ResourcePrecondition("repo/main.py", fp("a")),)
    )
    assert len(conditions.digest) == 64
    assert conditions.digest == conditions.digest


def test_preconditions_duplicate_resource_rejected():
    condition = ResourcePrecondition("x", fp("a"))
    with pytest.raises(ValueError):
        Preconditions((condition, condition))


def test_precondition_checker_match():
    conditions = Preconditions(
        (ResourcePrecondition("x", fp("a")),)
    )
    report = PreconditionChecker(lambda resource: fp("a")).inspect(conditions)
    assert report.ok
    assert report.drifted == ()


def test_precondition_checker_required_mismatch():
    conditions = Preconditions(
        (ResourcePrecondition("x", fp("a")),)
    )
    report = PreconditionChecker(lambda resource: fp("b")).inspect(conditions)
    assert not report.ok
    assert report.drifted == ("x",)


def test_precondition_checker_optional_mismatch_does_not_fail():
    conditions = Preconditions(
        (ResourcePrecondition("x", fp("a"), required=False),)
    )
    report = PreconditionChecker(lambda resource: fp("b")).inspect(conditions)
    assert report.ok
    assert report.drifted == ("x",)


def test_precondition_checker_provider_exception_fails_required():
    conditions = Preconditions(
        (ResourcePrecondition("x", fp("a")),)
    )

    def fail(resource):
        raise OSError("missing")

    report = PreconditionChecker(fail).inspect(conditions)
    assert not report.ok
    assert report.results[0].error == "OSError"


def test_precondition_checker_require_raises_on_drift():
    conditions = Preconditions(
        (ResourcePrecondition("x", fp("a")),)
    )
    with pytest.raises(RuntimeError, match="precondition drift"):
        PreconditionChecker(lambda resource: fp("b")).require(conditions)


def test_execution_seal_issue_verify():
    now = [10.0]
    authority = ExecutionSealAuthority(b"k" * 32, clock=lambda: now[0])
    seal = authority.issue(
        principal="alice",
        session_id="s",
        plan_pin=pin(),
        preconditions_digest=fp("9"),
        approval_id="approval",
        ttl_seconds=5,
    )
    authority.verify(
        seal,
        principal="alice",
        session_id="s",
        plan_pin=pin(),
        preconditions_digest=fp("9"),
        approval_id="approval",
    )
    assert seal.expires_at == 15


def test_execution_seal_expiry():
    now = [0.0]
    authority = ExecutionSealAuthority(b"k" * 32, clock=lambda: now[0])
    seal = authority.issue(
        principal="alice",
        session_id="s",
        plan_pin=pin(),
        ttl_seconds=1,
    )
    now[0] = 1
    with pytest.raises(ExecutionSealError, match="expired"):
        authority.verify(
            seal,
            principal="alice",
            session_id="s",
            plan_pin=pin(),
        )


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"principal": "bob"}, "principal"),
        ({"session_id": "other"}, "session"),
        ({"plan_pin": PlanPin(fp("9"), fp("b"), fp("c"), fp("d"), fp("e"), fp("f"), fp("1"))}, "plan pin"),
        ({"preconditions_digest": fp("8")}, "preconditions"),
        ({"approval_id": "other"}, "approval"),
    ],
)
def test_execution_seal_binding_mismatch(kwargs, match):
    authority = ExecutionSealAuthority(b"k" * 32)
    seal = authority.issue(
        principal="alice",
        session_id="s",
        plan_pin=pin(),
        preconditions_digest=fp("9"),
        approval_id="approval",
    )
    values = {
        "principal": "alice",
        "session_id": "s",
        "plan_pin": pin(),
        "preconditions_digest": fp("9"),
        "approval_id": "approval",
    }
    values.update(kwargs)
    with pytest.raises(ExecutionSealError, match=match):
        authority.verify(seal, **values)


def test_execution_seal_signature_tamper():
    authority = ExecutionSealAuthority(b"k" * 32)
    seal = authority.issue(
        principal="alice",
        session_id="s",
        plan_pin=pin(),
    )
    tampered = replace(seal, signature="0" * 64)
    with pytest.raises(ExecutionSealError, match="signature"):
        authority.verify(
            tampered,
            principal="alice",
            session_id="s",
            plan_pin=pin(),
        )


def test_execution_seal_registry_single_use():
    authority = ExecutionSealAuthority(b"k" * 32)
    registry = ExecutionSealRegistry(authority)
    seal = authority.issue(
        principal="alice",
        session_id="s",
        plan_pin=pin(),
    )
    use = registry.consume(
        seal,
        principal="alice",
        session_id="s",
        plan_pin=pin(),
    )
    assert registry.used(seal.seal_id)
    assert use.seal_id == seal.seal_id
    with pytest.raises(SealReplay):
        registry.consume(
            seal,
            principal="alice",
            session_id="s",
            plan_pin=pin(),
        )


def test_execution_seal_key_minimum():
    with pytest.raises(ValueError):
        ExecutionSealAuthority(b"short")


def test_execution_seal_ttl_cannot_exceed_authority_maximum():
    authority = ExecutionSealAuthority(
        b"k" * 32,
        max_ttl_seconds=10,
    )
    with pytest.raises(ValueError, match="maximum"):
        authority.issue(
            principal="alice",
            session_id="s",
            plan_pin=pin(),
            ttl_seconds=11,
        )


def test_execution_seal_rejects_issue_time_too_far_in_future():
    now = [10.0]
    authority = ExecutionSealAuthority(
        b"k" * 32,
        clock=lambda: now[0],
        max_clock_skew_seconds=1,
    )
    seal = authority.issue(
        principal="alice",
        session_id="s",
        plan_pin=pin(),
        ttl_seconds=5,
    )
    now[0] = 0.0
    with pytest.raises(ExecutionSealError, match="future"):
        authority.verify(
            seal,
            principal="alice",
            session_id="s",
            plan_pin=pin(),
        )
