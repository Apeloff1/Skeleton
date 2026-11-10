"""Canonical engine text identity framing and malformed input rejection.

Existing pipe-free input identities must not change: already admitted engine
executions depend on the historic stable UUID. Separator-bearing identities
must not let distinct accounts or retries collide during durable recovery.
"""
from __future__ import annotations

import math
from dataclasses import replace

import pytest

from core.engine_text import (
    EngineTextError,
    EngineTextRequest,
    _operation_identity_material,
    _stable_uuid,
)


def _request(*, tenant_id="a", actor_id="b", key="stable-key", **kwargs):
    values = {
        "instructions": "Preserve immutable assistant policy",
        "prompt": "Create a bounded game subsystem",
        "idempotency_key": key,
        "tenant_id": tenant_id,
        "actor_id": actor_id,
    }
    values.update(kwargs)
    return EngineTextRequest(**values)


def test_legacy_identity_recipe_remains_unchanged_for_pipe_free_authorities():
    request = _request(tenant_id="tenant", actor_id="actor", key="turn-5")
    material = _operation_identity_material(request)
    assert material == "tenant|actor|assistant.compat|turn-5"
    assert _stable_uuid("backend-engine-text-operation", material) == _stable_uuid(
        "backend-engine-text-operation",
        "tenant|actor|assistant.compat|turn-5",
    )


def test_separator_collision_between_tenant_and_actor_is_prevented():
    first = _request(tenant_id="alpha|beta", actor_id="gamma", key="turn")
    second = _request(tenant_id="alpha", actor_id="beta|gamma", key="turn")
    # The former pipe-delimited identity was identical for these accounts.
    assert "|".join((first.tenant_id, first.actor_id, first.capability, first.idempotency_key)) == (
        "|".join((second.tenant_id, second.actor_id, second.capability, second.idempotency_key))
    )
    one = _operation_identity_material(first)
    two = _operation_identity_material(second)
    assert one != two
    assert one.startswith("v2-framed-")
    assert two.startswith("v2-framed-")
    assert "|" not in one and "|" not in two
    assert _stable_uuid("backend-engine-text-operation", one) != _stable_uuid(
        "backend-engine-text-operation", two,
    )


def test_separator_collision_in_user_key_cannot_alias_actor_identity():
    first = _request(tenant_id="tenant|actor", actor_id="service", key="turn")
    second = _request(tenant_id="tenant", actor_id="actor|service", key="turn")
    assert _operation_identity_material(first) != _operation_identity_material(second)
    assert _operation_identity_material(first) == _operation_identity_material(
        _request(tenant_id="tenant|actor", actor_id="service", key="turn")
    )


def test_versioned_identity_cannot_equal_any_unambiguous_legacy_join():
    piped = _request(tenant_id="org|suborg")
    normal = _request(tenant_id="org", actor_id="suborg")
    assert _operation_identity_material(piped).startswith("v2-framed-")
    assert _operation_identity_material(normal).count("|") == 3
    assert _operation_identity_material(piped) != _operation_identity_material(normal)


@pytest.mark.parametrize("field,bad", [
    ("tenant_id", " tenant"),
    ("tenant_id", "tenant\n"),
    ("tenant_id", "tenant\x00name"),
    ("tenant_id", "tenant\u007fname"),
    ("tenant_id", "\ud800"),
    ("actor_id", "actor\rrole"),
    ("actor_id", "actor\tname"),
    ("actor_id", "actor "),
    ("idempotency_key", "job\nnext"),
    ("idempotency_key", "\njob"),
    ("idempotency_key", "job\0next"),
    ("idempotency_key", "job "),
    ("idempotency_key", "\udfff"),
])
def test_untrusted_identity_bytes_rejected_at_request_creation(field, bad):
    kwargs = {field: bad}
    with pytest.raises(EngineTextError):
        _request(**kwargs)


@pytest.mark.parametrize("bad", [
    "\ud800", "\udfff", "prefix \ud800 suffix",
])
def test_malformed_prompt_unicode_never_reaches_engine_compiler(bad):
    with pytest.raises(EngineTextError, match="Unicode"):
        _request(prompt=bad)


@pytest.mark.parametrize("bad", [
    10 ** 1000, float("inf"), -float("inf"), float("nan"),
    True, False, "1", -0.1, 2.01,
])
def test_temperature_bad_types_or_ranges_are_caught_without_float_overflow(bad):
    with pytest.raises(EngineTextError, match="temperature"):
        _request(temperature=bad)


@pytest.mark.parametrize("valid", [0, 0.0, 1, 1.0, 2, 2.0])
def test_temperature_valid_values_preserve_original_request_identity(valid):
    request = _request(temperature=valid)
    assert request.temperature == valid
    assert request.request_identity_digest
