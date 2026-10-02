"""Tests for the fail-closed capability-security gate."""

from __future__ import annotations

import sys
import types

import pytest

from .capsec import (
    B031_INTEGRATION_NOTE,
    AllowAllChecker,
    AllowListChecker,
    CapabilityDecision,
    CapabilityRequest,
    CapsecGate,
    CheckerChain,
    DenyAllChecker,
    implicit_capability,
    load_checker,
)
from .errors import CapabilityDeniedError, ConfigurationError


def req(principal="agent:a", tool="clock", caps=("time.read",), digest="d1") -> CapabilityRequest:
    return CapabilityRequest(principal=principal, tool=tool, capabilities=caps, arguments_digest=digest)


def test_request_always_includes_implicit_tool_capability():
    r = req(caps=())
    assert r.capabilities == (implicit_capability("clock"),)
    assert set(req().capabilities) == {"time.read", "tool.invoke:clock"}
    with pytest.raises(ConfigurationError):
        CapabilityRequest(principal="", tool="x", capabilities=())


def test_default_gate_is_fail_closed():
    gate = CapsecGate()
    assert gate.fail_closed_default
    decision = gate.decide(req())
    assert not decision.allowed
    assert set(decision.denied) == {"time.read", "tool.invoke:clock"}
    with pytest.raises(CapabilityDeniedError) as info:
        gate.enforce(req())
    assert info.value.reason.startswith("no capability checker configured")
    assert info.value.details["checker"] == "deny_all"


def test_allow_all_is_explicit_opt_in():
    gate = CapsecGate(AllowAllChecker())
    assert not gate.fail_closed_default
    assert gate.enforce(req()).allowed


def test_allow_list_grants_globs_per_principal():
    checker = AllowListChecker(
        {"agent:a": ["tool.invoke:*", "time.*"], "*": ["tool.invoke:echo"]},
        deny={"agent:a": ["tool.invoke:shell"]},
    )
    assert checker.check(req()).allowed
    assert not checker.check(req(principal="agent:b")).allowed
    assert checker.check(req(principal="agent:b", tool="echo", caps=())).allowed
    denied = checker.check(req(tool="shell", caps=()))
    assert not denied.allowed and denied.reason == "explicitly denied"
    missing = checker.check(req(caps=("fs.write",)))
    assert missing.denied == ("fs.write",)


def test_checker_exceptions_and_garbage_are_denials():
    class Crashy:
        def check(self, request):
            raise RuntimeError("bug")

    class Garbage:
        def check(self, request):
            return True

    class Sneaky:
        def check(self, request):
            return CapabilityDecision(True, granted=("tool.invoke:clock",))

    for checker in (Crashy(), Garbage(), Sneaky()):
        decision = CapsecGate(checker).decide(req())
        assert not decision.allowed, type(checker).__name__


def test_chain_requires_every_checker():
    allow = AllowAllChecker()
    narrow = AllowListChecker({"*": ["tool.invoke:*"]})
    assert not CheckerChain([]).check(req()).allowed
    assert CheckerChain([allow, AllowListChecker({"*": ["*"]})]).check(req()).allowed
    decision = CheckerChain([allow, narrow]).check(req())
    assert not decision.allowed and decision.denied == ("time.read",)


def test_audit_trail_records_digest_only_and_is_bounded():
    gate = CapsecGate(AllowAllChecker(), audit_limit=2)
    for i in range(3):
        gate.decide(req(digest=f"d{i}"))
    records = gate.audit()
    assert [r.arguments_digest for r in records] == ["d1", "d2"]
    assert gate.audit(limit=1)[0].arguments_digest == "d2"
    payload = records[0].as_dict()
    assert set(payload) == {
        "at",
        "principal",
        "tool",
        "capabilities",
        "allowed",
        "reason",
        "checker",
        "arguments_digest",
    }


def test_load_checker_builtins_and_specs():
    assert isinstance(load_checker("deny_all"), DenyAllChecker)
    assert isinstance(load_checker("allow_all"), AllowAllChecker)
    module = types.ModuleType("capsec_test_plugin")

    class Plugin:
        def __init__(self, level: int = 0) -> None:
            self.level = level

        def check(self, request):
            return CapabilityDecision.allow(request.capabilities, checker="plugin")

    module.Plugin = Plugin  # type: ignore[attr-defined]
    module.instance = Plugin(3)  # type: ignore[attr-defined]
    module.not_a_checker = object()  # type: ignore[attr-defined]

    def broken_factory():
        raise RuntimeError("nope")

    module.broken_factory = broken_factory  # type: ignore[attr-defined]
    sys.modules["capsec_test_plugin"] = module
    try:
        built = load_checker("capsec_test_plugin:Plugin", level=2)
        assert built.level == 2  # type: ignore[attr-defined]
        assert load_checker("capsec_test_plugin:instance").level == 3  # type: ignore[attr-defined]
        with pytest.raises(ConfigurationError):
            load_checker("capsec_test_plugin:not_a_checker")
        with pytest.raises(ConfigurationError):
            load_checker("capsec_test_plugin:broken_factory")
        with pytest.raises(ConfigurationError):
            load_checker("capsec_test_plugin:missing")
        with pytest.raises(ConfigurationError):
            load_checker("no.such.module:thing")
        with pytest.raises(ConfigurationError):
            load_checker("missing-colon")
    finally:
        sys.modules.pop("capsec_test_plugin", None)


def test_b031_note_documents_assumption():
    assert "fail-closed" in B031_INTEGRATION_NOTE
    assert "module:attr" in B031_INTEGRATION_NOTE
