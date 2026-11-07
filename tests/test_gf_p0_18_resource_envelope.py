"""GF-P0-18: deadlines and bounded-memory resource envelopes."""

from __future__ import annotations

import asyncio

import pytest

from skeleton.provider_environment import (
    EnvironmentIdentity, HoldoutSplit, buffers_for_envelope, make_record, route_records,
)
from skeleton.provider_runtime import (
    EnvelopedProviderAdapter, ModelReadinessGate, ProviderAdapter,
    ProviderInvocationError, ProviderPolicyError, ProviderRequest, ResourceEnvelope,
)


def test_envelope_validation():
    for kw in ({"max_seconds": 0}, {"max_seconds": 4000}, {"max_buffer_bytes": 0}):
        with pytest.raises(ValueError):
            ResourceEnvelope(**kw)


class _Slow(ProviderAdapter):
    provider_id, model = "local", "m1"

    @property
    def available(self):
        return True

    async def generate(self, request):
        await asyncio.sleep(5)
        return "late"


class _Gate(ModelReadinessGate):
    def __init__(self, allow):
        self.allow = allow

    def check(self, provider_id, model, *, use=None):
        if not self.allow:
            raise ProviderPolicyError("denied")


def test_deadline_enforced():
    a = EnvelopedProviderAdapter(_Slow(), _Gate(True), ResourceEnvelope(max_seconds=0.05))
    with pytest.raises(ProviderInvocationError, match="deadline"):
        asyncio.run(a.generate(ProviderRequest(instructions="i", prompt="p")))


def test_enveloped_adapter_still_gated():
    a = EnvelopedProviderAdapter(_Slow(), _Gate(False), ResourceEnvelope(max_seconds=1))
    with pytest.raises(ProviderPolicyError):
        asyncio.run(a.generate(ProviderRequest(instructions="i", prompt="p")))


def test_bounded_memory_byte_envelope():
    split = HoldoutSplit(salt="s", holdout_fraction=0.3)
    env = ResourceEnvelope(max_buffer_bytes=4096)
    replay, hold = buffers_for_envelope(split, env, max_items=100_000)
    ident = EnvironmentIdentity("g", "b", 1)
    route_records((make_record(f"e{i}", ident, {"blob": "x" * 100}) for i in range(10_000)), replay, hold)
    assert replay.retained_bytes <= replay.max_bytes
    assert hold.retained_bytes <= hold.max_bytes
    assert replay.retained_bytes + hold.retained_bytes <= env.max_buffer_bytes
    assert len(replay) < 100 and len(hold) < 100


def test_oversized_record_rejected():
    split = HoldoutSplit(salt="s", holdout_fraction=0.3)
    replay, _ = buffers_for_envelope(split, ResourceEnvelope(max_buffer_bytes=200), max_items=10)
    rec = next(make_record(f"e{i}", EnvironmentIdentity("g", "b", 1), {"blob": "x" * 500})
               for i in range(100) if not split.is_holdout(f"e{i}"))
    with pytest.raises(ValueError):
        replay.add(rec)
