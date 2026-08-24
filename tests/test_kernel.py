"""Tests for the kernel: events, ids, registry, errors."""

import pytest

from skeleton.kernel.errors import (
    CapabilityNotFoundError,
    DuplicateCapabilityError,
    InvalidIdentifierError,
    RegistryError,
    SkeletonError,
    http_status_for,
)
from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.kernel.ids import AgentId, SessionId, parse_any
from skeleton.kernel.registry import CapabilityKind, CapabilityRegistry, bootstrap_registry


class TestEventBus:
    def test_publish_and_subscribe(self):
        bus = EventBus()
        seen = []
        bus.subscribe("pipeline.*", seen.append)
        bus.emit("pipeline.npc.completed", {"ok": True})
        assert len(seen) == 1
        assert seen[0].payload["ok"] is True

    def test_correlation_threading(self):
        first = DomainEvent(topic="a", payload={})
        second = first.derive("b", {})
        assert second.correlation_id == first.correlation_id
        assert second.causation_id == first.event_id

    def test_handler_failure_isolated(self):
        bus = EventBus()
        bus.subscribe("x", lambda e: 1 / 0)
        ok = []
        bus.subscribe("x", ok.append)
        failures = bus.publish(DomainEvent(topic="x", payload={}))
        assert len(failures) == 1
        assert len(ok) == 1

    def test_replay(self):
        bus = EventBus()
        bus.emit("a.b", {})
        seen = []
        bus.subscribe("a.*", seen.append, replay=True)
        assert len(seen) == 1


class TestIds:
    def test_roundtrip(self):
        agent = AgentId.new()
        assert AgentId.parse(str(agent)) == agent

    def test_wrong_prefix_rejected(self):
        with pytest.raises(InvalidIdentifierError):
            SessionId.parse(str(AgentId.new()))

    def test_parse_any(self):
        sess = SessionId.new()
        assert parse_any(str(sess)) == sess

    def test_kinds_do_not_compare_equal(self):
        assert AgentId.new() != SessionId.new()


class TestRegistry:
    def test_register_and_get(self):
        reg = CapabilityRegistry()
        reg.register("npc", CapabilityKind.PIPELINE, "16.0.0")
        assert reg.get(CapabilityKind.PIPELINE, "npc").version.major == 16

    def test_duplicate_rejected(self):
        reg = CapabilityRegistry()
        reg.register("npc", CapabilityKind.PIPELINE, "16.0.0")
        with pytest.raises(DuplicateCapabilityError):
            reg.register("npc", CapabilityKind.PIPELINE, "16.0.0")

    def test_missing_raises(self):
        reg = CapabilityRegistry()
        with pytest.raises(CapabilityNotFoundError):
            reg.get(CapabilityKind.PIPELINE, "nope")

    def test_semver_validation(self):
        reg = CapabilityRegistry()
        with pytest.raises(RegistryError):
            reg.register("bad", CapabilityKind.TOOL, "1.0")

    def test_bootstrap(self):
        reg = bootstrap_registry(EventBus())
        assert reg.has(CapabilityKind.PIPELINE, "npc")
        assert reg.has(CapabilityKind.FORGE_BLUEPRINT, "universal")


class TestErrors:
    def test_to_dict(self):
        err = SkeletonError("boom", context={"x": 1})
        d = err.to_dict()
        assert d["code"] == "SKL.UNKNOWN"
        assert d["context"] == {"x": 1}

    def test_http_mapping(self):
        assert http_status_for(CapabilityNotFoundError("x")) == 404
        assert http_status_for(SkeletonError("x")) == 500
