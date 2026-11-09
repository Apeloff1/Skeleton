from __future__ import annotations

import pytest

from skeleton.security.policy_engine import PolicyEngine


def test_unknown_policy_fails_closed() -> None:
    decision = PolicyEngine().evaluate("missing", {"actor": "operator"})
    assert decision.allowed is False
    assert decision.effect == "deny"
    assert "fail-safe deny" in decision.reason


def test_defined_policy_defaults_to_deny_when_no_rule_matches() -> None:
    engine = PolicyEngine()
    engine.define("deploy")
    engine.add_rule("deploy", "allow-admin", lambda ctx: ctx.get("role") == "admin", effect="allow")
    decision = engine.evaluate("deploy", {"role": "viewer"})
    assert decision.allowed is False
    assert decision.effect == "deny"
    assert decision.reason == "no rules matched — default"


def test_rule_exception_cannot_turn_into_allow() -> None:
    engine = PolicyEngine()
    engine.define("secret-read")

    def broken(_context):
        raise RuntimeError("backend exploded")

    engine.add_rule("secret-read", "broken", broken, effect="allow")
    decision = engine.evaluate("secret-read", {})
    assert decision.allowed is False
    assert decision.effect == "deny"


def test_explicit_allow_rule_is_required_for_default_policy() -> None:
    engine = PolicyEngine()
    engine.define("threshold-change")
    engine.add_rule(
        "threshold-change",
        "approved",
        lambda ctx: ctx.get("approved") is True,
        effect="allow",
    )
    assert engine.evaluate("threshold-change", {"approved": True}).allowed is True
    assert engine.evaluate("threshold-change", {"approved": False}).allowed is False


@pytest.mark.parametrize("combinator", ["", "or", "ALL"])
def test_invalid_combinator_is_rejected(combinator: str) -> None:
    with pytest.raises(ValueError, match="combinator"):
        PolicyEngine().define("x", combinator=combinator)


@pytest.mark.parametrize("default", ["", "permit", "unknown"])
def test_invalid_default_is_rejected(default: str) -> None:
    with pytest.raises(ValueError, match="default"):
        PolicyEngine().define("x", default=default)


def test_invalid_rule_effect_is_rejected() -> None:
    engine = PolicyEngine()
    engine.define("x")
    with pytest.raises(ValueError, match="effect"):
        engine.add_rule("x", "bad", lambda _ctx: True, effect="permit")
