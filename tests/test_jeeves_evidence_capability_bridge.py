from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from skeleton.jeeves.evidence_core import EvidenceJeevesCore


class CapturingProvider:
    name = "capture"
    supports_system_prompt = True

    def __init__(self) -> None:
        self.prompt = ""
        self.system = ""

    def complete(self, prompt, context=None, system=None):
        self.prompt = prompt
        self.system = system or ""
        return "grounded"


@dataclass(frozen=True)
class FakeSpec:
    name: str
    mutates: bool = False
    approval_required: bool = False
    evidence_required: bool = True
    tags: frozenset[str] = field(default_factory=frozenset)


class FakeRegistry:
    def __init__(self, specs):
        self._specs = {spec.name: spec for spec in specs}

    def snapshot(self):
        return [
            {
                "name": spec.name,
                "mutates": spec.mutates,
                "approval_required": spec.approval_required,
                "evidence_required": spec.evidence_required,
                "tags": sorted(spec.tags),
            }
            for spec in self._specs.values()
        ]

    def get(self, name):
        return self._specs.get(name)


def _core():
    provider = CapturingProvider()
    core = EvidenceJeevesCore(provider=provider, evidence_clock=lambda: 1_000.0)
    session = core.open_session("learner")
    return core, session, provider


def test_registry_bridge_attaches_only_read_only_unapproved_capabilities():
    core, session, _ = _core()
    registry = FakeRegistry(
        [
            FakeSpec("market_read", tags=frozenset({"market", "read"})),
            FakeSpec("write_file", mutates=True),
            FakeSpec("private_read", approval_required=True),
        ]
    )
    calls = []

    def invoker(name, arguments, request):
        calls.append((name, arguments, request))
        return {"symbol": arguments["symbol"], "price": 42.5}

    report = core.attach_capability_registry(registry, invoker)

    assert report == {
        "registered": 1,
        "skipped_mutating": 1,
        "skipped_approval": 1,
    }

    result = core.ask_with_evidence(
        session.session_id,
        "Use the market evidence.",
        context={
            "tool_calls": [
                {"name": "market_read", "arguments": {"symbol": "TEST"}},
            ]
        },
        allowed_tools=["market_read"],
    )

    assert len(calls) == 1
    assert calls[0][0] == "market_read"
    assert calls[0][1] == {"symbol": "TEST"}
    assert calls[0][2]["session"]["session_id"] == session.session_id
    assert result["tools"] == ["market_read"]
    assert result["evidence"][0]["source"] == "capability_registry"
    assert result["evidence"][0]["tags"] == ["market", "read"]
    assert len(result["evidence"][0]["sha256"]) == 64
    assert result["evidence"][0]["result"]["provenance"]["source_id"] == (
        "capability_registry/market_read"
    )
    assert result["evidence_receipts"] == [
        {
            "name": "market_read",
            "sha256": result["evidence"][0]["sha256"],
            "source": "capability_registry",
            "tags": ["market", "read"],
        }
    ]
    assert core.stats()["evidence_registry_tools"] == 1


def test_registry_mutating_capability_cannot_be_requested_as_evidence():
    core, session, _ = _core()
    registry = FakeRegistry([FakeSpec("write_file", mutates=True)])

    core.attach_capability_registry(
        registry,
        lambda name, arguments, request: {"should_not": "run"},
    )

    with pytest.raises(ValueError, match="unknown or invalid tool"):
        core.ask_with_evidence(
            session.session_id,
            "Try a write.",
            context={"tool_calls": [{"name": "write_file"}]},
            allowed_tools=["write_file"],
        )

    assert session.turns == []


def test_registry_bridge_conflict_preflight_is_atomic():
    core, session, _ = _core()
    core.register_evidence_tool("existing", lambda payload: {"ok": True})
    registry = FakeRegistry(
        [
            FakeSpec("new_read"),
            FakeSpec("existing"),
        ]
    )

    with pytest.raises(ValueError, match="conflicts with an existing Jeeves tool"):
        core.attach_capability_registry(
            registry,
            lambda name, arguments, request: {"ok": True},
        )

    with pytest.raises(ValueError, match="unknown or invalid tool"):
        core.ask_with_evidence(
            session.session_id,
            "No partial attachment.",
            context={"tool_calls": [{"name": "new_read"}]},
            allowed_tools=["new_read"],
        )

    assert session.turns == []


def test_registry_bridge_rejects_duplicate_names_after_normalization_atomically():
    core, session, _ = _core()
    registry = FakeRegistry(
        [
            FakeSpec("Read_Status"),
            FakeSpec("read_status"),
        ]
    )

    with pytest.raises(ValueError, match="duplicate tool name"):
        core.attach_capability_registry(
            registry,
            lambda name, arguments, request: {"ok": True},
        )

    with pytest.raises(ValueError, match="unknown or invalid tool"):
        core.ask_with_evidence(
            session.session_id,
            "No duplicates.",
            context={"tool_calls": [{"name": "read_status"}]},
            allowed_tools=["read_status"],
        )

    assert session.turns == []


def test_evidence_receipt_is_stable_for_same_source_content():
    core, first, _ = _core()
    core.register_evidence_tool(
        "lookup",
        lambda payload: {"b": 2, "a": 1},
        source_id="fixture.lookup",
    )

    one = core.ask_with_evidence(
        first.session_id,
        "First lookup.",
        context={"tool_calls": [{"name": "lookup"}]},
        allowed_tools=["lookup"],
    )
    second_session = core.open_session("learner-2")
    two = core.ask_with_evidence(
        second_session.session_id,
        "Second lookup.",
        context={"tool_calls": [{"name": "lookup"}]},
        allowed_tools=["lookup"],
    )

    assert one["evidence"][0]["sha256"] == two["evidence"][0]["sha256"]
    assert one["evidence_receipts"][0]["sha256"] == one["evidence"][0]["sha256"]
    assert first.turns[-1].metadata["evidence_receipts"] == one["evidence_receipts"]


def test_registry_invoker_failure_is_redacted_and_not_receipted():
    core, session, _ = _core()
    registry = FakeRegistry([FakeSpec("lookup")])

    def fail(name, arguments, request):
        raise RuntimeError("secret runtime detail")

    core.attach_capability_registry(registry, fail)
    result = core.ask_with_evidence(
        session.session_id,
        "Use lookup.",
        context={"tool_calls": [{"name": "lookup"}]},
        allowed_tools=["lookup"],
    )

    assert result["tools"] == []
    assert result["evidence"] == []
    assert result["evidence_receipts"] == []
    assert result["tool_errors"] == [{"name": "lookup", "error": "execution_failed"}]
    assert "secret runtime detail" not in result["content"]


def test_registry_contract_validation_happens_before_attachment():
    core, _, _ = _core()

    class BadRegistry:
        def snapshot(self):
            return {"name": "not-a-list"}

        def get(self, name):
            return None

    with pytest.raises(ValueError, match="snapshot must be a list"):
        core.attach_capability_registry(
            BadRegistry(),
            lambda name, arguments, request: {"ok": True},
        )

    with pytest.raises(TypeError, match="invoker must be callable"):
        core.attach_capability_registry(FakeRegistry([]), object())


@pytest.mark.parametrize(
    ("replacement", "expected_error"),
    [
        (FakeSpec("lookup", mutates=True), "capability_became_mutating"),
        (FakeSpec("lookup", approval_required=True), "capability_requires_approval"),
    ],
)
def test_live_registry_policy_is_revalidated_before_each_invocation(
    replacement,
    expected_error,
):
    core, session, _ = _core()
    registry = FakeRegistry([FakeSpec("lookup")])
    calls = []

    core.attach_capability_registry(
        registry,
        lambda name, arguments, request: calls.append(name) or {"ok": True},
    )
    registry._specs["lookup"] = replacement

    result = core.ask_with_evidence(
        session.session_id,
        "Use lookup after policy changed.",
        context={"tool_calls": [{"name": "lookup"}]},
        allowed_tools=["lookup"],
    )

    assert calls == []
    assert result["tools"] == []
    assert result["evidence"] == []
    assert result["evidence_receipts"] == []
    assert result["tool_errors"] == [{"name": "lookup", "error": expected_error}]
    assert core.stats()["evidence_policy_failures"] == 1


def test_removed_registry_capability_fails_closed_before_invoker():
    core, session, _ = _core()
    registry = FakeRegistry([FakeSpec("lookup")])
    calls = []

    core.attach_capability_registry(
        registry,
        lambda name, arguments, request: calls.append(name) or {"ok": True},
    )
    registry._specs.pop("lookup")

    result = core.ask_with_evidence(
        session.session_id,
        "Use a removed lookup.",
        context={"tool_calls": [{"name": "lookup"}]},
        allowed_tools=["lookup"],
    )

    assert calls == []
    assert result["tool_errors"] == [{"name": "lookup", "error": "capability_unavailable"}]
    assert result["evidence"] == []
    assert core.stats()["evidence_policy_failures"] == 1
