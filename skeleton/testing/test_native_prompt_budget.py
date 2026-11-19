"""Deterministic per-tenant native prompt RAM custody regression tests."""
from __future__ import annotations

from dataclasses import replace
import pytest

from skeleton.cortex.transformer import TinyTransformer
from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.native_fair_stream_backend import (
    NativeFairStreamDenied, NativePromptRegistry, pin_native_prompt,
)
from skeleton.ai.model_runtime.native_prompt_budget import (
    NativePromptBudget, PromptBudgetDenied, PromptBudgetLedger,
)

SESSION = "a" * 32


def grant(runtime, tenant, request, prompt="hello"):
    return pin_native_prompt(
        runtime, session_id=SESSION, tenant_id=tenant,
        request_id=request, prompt=prompt, max_output_tokens=1,
    )


def runtime():
    return NativeLLMRuntime(TinyTransformer(vocab=("hello", "world"), ctx=24))


@pytest.mark.parametrize("bad", [0, -1, True, 17 << 20, 1.2])
def test_invalid_total_ram_cap_denied(bad):
    with pytest.raises(ValueError):
        NativePromptBudget(max_staged_bytes=bad)


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, 257])
def test_invalid_per_tenant_count_denied(bad):
    with pytest.raises(ValueError):
        NativePromptBudget(max_staged_per_tenant=bad)


def test_tenant_and_global_memory_caps_are_independent():
    ledger = PromptBudgetLedger(NativePromptBudget(
        max_staged_bytes=12, max_staged_bytes_per_tenant=8,
        max_staged_per_tenant=2,
    ))
    ledger.reserve("alice", 5)
    with pytest.raises(PromptBudgetDenied):
        ledger.reserve("alice", 4)
    ledger.reserve("bob", 7)
    with pytest.raises(PromptBudgetDenied):
        ledger.reserve("carol", 1)
    assert ledger.snapshot()["staged_bytes"] == 12
    ledger.release("alice", 5)
    ledger.reserve("carol", 1)
    assert ledger.snapshot()["active_tenants"] == 2


def test_failed_release_does_not_create_capacity():
    ledger = PromptBudgetLedger(NativePromptBudget(
        max_staged_bytes=10, max_staged_bytes_per_tenant=10,
    ))
    ledger.reserve("alice", 4)
    for tenant, size in (("bob", 1), ("alice", 5), ("alice", 0)):
        with pytest.raises(PromptBudgetDenied):
            ledger.release(tenant, size)
    assert ledger.snapshot()["staged_bytes"] == 4
    ledger.release("alice", 4)
    assert ledger.snapshot()["staged_bytes"] == 0


def test_registry_reserves_and_releases_real_utf8_bytes():
    model = runtime()
    registry = NativePromptRegistry(session_id=SESSION, budget=NativePromptBudget(
        max_staged_bytes=10, max_staged_bytes_per_tenant=5,
        max_staged_per_tenant=1,
    ))
    registry.stage(grant(model, "alice", "one"))
    assert registry.budget_status()["staged_bytes"] == 5
    with pytest.raises(PromptBudgetDenied):
        registry.stage(grant(model, "alice", "two"))
    registry.stage(grant(model, "bob", "three"))
    assert registry.budget_status()["staged_bytes"] == 10
    with pytest.raises(PromptBudgetDenied):
        registry.stage(grant(model, "carol", "four"))
    registry.revoke("one")
    assert registry.budget_status()["staged_bytes"] == 5
    with pytest.raises(NativeFairStreamDenied):
        registry.stage(grant(model, "alice", "one"))
    registry.stage(grant(model, "alice", "new"))
    assert registry.budget_status()["staged_bytes"] == 10
    assert registry.claim("three", "bob").request_id == "three"
    assert registry.budget_status()["staged_bytes"] == 5
    assert registry.status()["staged_prompt_bytes"] == 5


def test_wrong_tenant_claim_never_releases_other_tenant_reservation():
    model = runtime()
    registry = NativePromptRegistry(session_id=SESSION)
    registry.stage(grant(model, "alice", "one"))
    with pytest.raises(NativeFairStreamDenied):
        registry.claim("one", "bob")
    assert registry.budget_status()["staged_bytes"] == 5
    assert registry.claim("one", "alice").request_id == "one"
    assert registry.budget_status()["staged_bytes"] == 0


def test_status_is_payload_free_and_does_not_expose_tenant_ids():
    model = runtime()
    registry = NativePromptRegistry(session_id=SESSION)
    registry.stage(grant(model, "sensitive-tenant", "sensitive-request"))
    snapshot = str(registry.budget_status())
    assert "sensitive-tenant" not in snapshot
    assert "sensitive-request" not in snapshot
    assert "hello" not in snapshot


def test_revoke_unknown_burns_identity_without_charging_memory():
    model = runtime()
    registry = NativePromptRegistry(session_id=SESSION)
    registry.revoke("burned")
    assert registry.budget_status()["staged_bytes"] == 0
    with pytest.raises(NativeFairStreamDenied):
        registry.stage(grant(model, "alice", "burned"))


def test_accounting_corruption_fails_closed():
    ledger = PromptBudgetLedger(NativePromptBudget())
    ledger.reserve("alice", 3)
    ledger._bytes = 0
    with pytest.raises(PromptBudgetDenied, match="invariant"):
        ledger.reserve("bob", 2)
    with pytest.raises(PromptBudgetDenied, match="invariant"):
        ledger.snapshot()


@pytest.mark.parametrize("tenant", ["\ud800", "", "bad\nidentity"])
def test_untrusted_tenant_identity_is_denied(tenant):
    ledger = PromptBudgetLedger(NativePromptBudget())
    with pytest.raises(PromptBudgetDenied):
        ledger.reserve(tenant, 1)
    assert ledger.snapshot()["staged_bytes"] == 0


def test_corrupt_multi_grant_release_does_not_partially_mutate():
    ledger = PromptBudgetLedger(NativePromptBudget())
    ledger.reserve("alice", 3)
    ledger.reserve("alice", 3)
    with pytest.raises(PromptBudgetDenied):
        ledger.release("alice", 6)
    assert ledger.snapshot()["staged_bytes"] == 6
    ledger.release("alice", 3)
    ledger.release("alice", 3)
    assert ledger.snapshot()["staged_grants"] == 0


def test_expired_prompt_releases_ram_but_never_replays_identity():
    from unittest.mock import patch
    model = runtime()
    registry = NativePromptRegistry(session_id=SESSION,
        max_stage_age_ns=10, budget=NativePromptBudget(
            max_staged_bytes=5, max_staged_bytes_per_tenant=5))
    with patch("skeleton.ai.model_runtime.native_fair_stream_backend.monotonic_ns",
               side_effect=[100, 110, 110, 110, 110]):
        registry.stage(grant(model, "alice", "one"))
        assert registry.status()["staged"] == 0
        assert registry.budget_status()["staged_bytes"] == 0
        with pytest.raises(NativeFairStreamDenied, match="missing authorized"):
            registry.claim("one", "alice")
        with pytest.raises(NativeFairStreamDenied, match="duplicate or consumed"):
            registry.stage(grant(model, "alice", "one"))


def test_expiry_reclaims_tenant_capacity_for_new_request():
    from unittest.mock import patch
    model = runtime()
    registry = NativePromptRegistry(session_id=SESSION,
        max_stage_age_ns=10, budget=NativePromptBudget(
            max_staged_bytes=5, max_staged_bytes_per_tenant=5))
    with patch("skeleton.ai.model_runtime.native_fair_stream_backend.monotonic_ns",
               side_effect=[100, 111, 111, 111]):
        registry.stage(grant(model, "alice", "one"))
        registry.stage(grant(model, "bob", "two"))
        assert registry.budget_status()["staged_bytes"] == 5
        assert registry.claim("two", "bob").request_id == "two"


def test_prompt_claim_before_deadline_succeeds_once():
    from unittest.mock import patch
    model = runtime()
    registry = NativePromptRegistry(session_id=SESSION, max_stage_age_ns=10)
    with patch("skeleton.ai.model_runtime.native_fair_stream_backend.monotonic_ns",
               side_effect=[100, 109]):
        registry.stage(grant(model, "alice", "one"))
        assert registry.claim("one", "alice").request_id == "one"


@pytest.mark.parametrize("invalid", [0, -1, True, 1.5, 3_600_000_000_001])
def test_invalid_staging_lifetime_denied(invalid):
    with pytest.raises(NativeFairStreamDenied, match="lifetime"):
        NativePromptRegistry(session_id=SESSION, max_stage_age_ns=invalid)


@pytest.mark.parametrize("invalid_clock", [True, -1, "unknown"])
def test_unknown_prompt_clock_fails_closed_without_grant(invalid_clock):
    from unittest.mock import patch
    model = runtime()
    registry = NativePromptRegistry(session_id=SESSION)
    with patch("skeleton.ai.model_runtime.native_fair_stream_backend.monotonic_ns",
               return_value=invalid_clock):
        with pytest.raises(NativeFairStreamDenied, match="clock"):
            registry.stage(grant(model, "alice", "one"))
    assert registry._staged == {}


def test_clock_regression_denies_claim_without_releasing_grant():
    from unittest.mock import patch
    model = runtime()
    registry = NativePromptRegistry(session_id=SESSION)
    with patch("skeleton.ai.model_runtime.native_fair_stream_backend.monotonic_ns",
               side_effect=[100, 99]):
        registry.stage(grant(model, "alice", "one"))
        with pytest.raises(NativeFairStreamDenied, match="clock"):
            registry.claim("one", "alice")
    assert registry._staged["one"].tenant_id == "alice"


def test_timestamp_registry_corruption_denies_telemetry_and_claim():
    model = runtime()
    registry = NativePromptRegistry(session_id=SESSION)
    registry.stage(grant(model, "alice", "one"))
    registry._staged_at.clear()
    with pytest.raises(NativeFairStreamDenied, match="timestamp invariant"):
        registry.status()
    with pytest.raises(NativeFairStreamDenied, match="timestamp invariant"):
        registry.claim("one", "alice")


def test_surrogate_tenant_or_request_is_typed_denial():
    model = runtime()
    registry = NativePromptRegistry(session_id=SESSION)
    with pytest.raises(NativeFairStreamDenied):
        registry.revoke("\ud800")
    with pytest.raises(NativeFairStreamDenied):
        grant(model, "\ud800", "one")

def test_release_must_match_an_actual_reservation():
    ledger = PromptBudgetLedger(NativePromptBudget())
    ledger.reserve("alice", 2)
    ledger.reserve("alice", 7)
    before = ledger.snapshot()
    for false_size in (1, 3, 8):
        with pytest.raises(PromptBudgetDenied, match="unowned"):
            ledger.release("alice", false_size)
        assert ledger.snapshot() == before
    ledger.release("alice", 2)
    with pytest.raises(PromptBudgetDenied, match="unowned"):
        ledger.release("alice", 2)
    ledger.release("alice", 7)
    assert ledger.snapshot()["staged_grants"] == 0


def test_prompt_accounting_global_count_bounds_tiny_cross_tenant_grants(monkeypatch):
    from skeleton.ai.model_runtime import native_prompt_budget as module

    monkeypatch.setattr(module, "MAX_TOTAL_PROMPT_COUNT", 3)
    ledger = PromptBudgetLedger(NativePromptBudget())
    for tenant in ("a", "b", "c"):
        ledger.reserve(tenant, 1)
    before = ledger.snapshot()
    with pytest.raises(PromptBudgetDenied, match="admission"):
        ledger.reserve("d", 1)
    assert ledger.snapshot() == before
    ledger.release("b", 1)
    ledger.reserve("d", 1)
    assert ledger.snapshot()["staged_grants"] == 3


def test_prompt_size_inventory_corruption_fails_closed():
    ledger = PromptBudgetLedger(NativePromptBudget())
    ledger.reserve("alice", 2)
    ledger.reserve("alice", 7)
    ledger._sizes["alice"] = {3: 1, 7: 1}
    with pytest.raises(PromptBudgetDenied, match="invariant"):
        ledger.release("alice", 7)
    with pytest.raises(PromptBudgetDenied, match="invariant"):
        ledger.snapshot()
    assert ledger._bytes == 9


def test_inherited_prompt_ledger_denies_before_lock(monkeypatch):
    import os

    ledger = PromptBudgetLedger(NativePromptBudget())
    ledger.reserve("alice", 1)

    class Forbidden:
        def __enter__(self):
            pytest.fail("inherited prompt ledger reached lock")

    ledger._lock = Forbidden()
    parent = os.getpid()
    monkeypatch.setattr(os, "getpid", lambda: parent + 1)
    for operation in (ledger.snapshot, lambda: ledger.reserve("alice", 1),
                      lambda: ledger.release("alice", 1)):
        with pytest.raises(PromptBudgetDenied, match="inherited"):
            operation()

def test_clock_recovery_cannot_reanimate_old_prompt_authority(monkeypatch):
    from skeleton.ai.model_runtime import native_fair_stream_backend as module

    model = runtime()
    registry = NativePromptRegistry(session_id=SESSION)
    readings = iter((100, 99, 101))
    monkeypatch.setattr(module, "monotonic_ns", lambda: next(readings))
    registry.stage(grant(model, "alice", "one"))
    with pytest.raises(NativeFairStreamDenied, match="clock regressed"):
        registry.claim("one", "alice")
    with pytest.raises(NativeFairStreamDenied, match="clock authority invalidated"):
        registry.claim("one", "alice")
    registry.discard_cancelled("one")
    assert registry._staged == {}
    assert registry._budget.snapshot()["staged_grants"] == 0
    assert registry._used == {"one"}


def test_registry_accounting_drift_denies_claim_before_burning_grant():
    model = runtime()
    registry = NativePromptRegistry(session_id=SESSION)
    registry.stage(grant(model, "alice", "one"))
    registry._budget.reserve("alice", 1)
    with pytest.raises(NativeFairStreamDenied, match="custody invariant"):
        registry.claim("one", "alice")
    assert "one" in registry._staged
    assert "one" not in registry._used


def test_duplicate_durable_queue_identity_denied_before_claim():
    from skeleton.ai.model_runtime.fair_stream_queue import StreamRequest
    from skeleton.ai.model_runtime.iteration_scheduler import InferencePhase

    model = runtime()
    registry = NativePromptRegistry(session_id=SESSION)
    registry.stage(grant(model, "alice", "one"))
    bound = registry.bind_request(StreamRequest("one", "alice", InferencePhase.PREFILL, 1, 16))
    row = {
        "request_id": bound.request_id, "tenant_id": bound.tenant_id,
        "remaining_tokens": bound.remaining_tokens, "bytes_per_token": bound.bytes_per_token,
        "phase": bound.phase.value, "priority": bound.priority,
        "authorization_digest": bound.authorization_digest,
    }
    with pytest.raises(NativeFairStreamDenied, match="duplicate queued"):
        registry.verify_queued([row, dict(row)])
    assert registry.status()["staged"] == 1


@pytest.mark.parametrize("invalid", [False, 0, {}, ""])
def test_registry_cannot_default_invalid_budget(invalid):
    with pytest.raises(ValueError, match="canonical"):
        NativePromptRegistry(session_id=SESSION, budget=invalid)
