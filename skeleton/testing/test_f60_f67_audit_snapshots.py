"""Regression coverage for F-60..F-67 fail-closed identity slices."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from skeleton.__main__ import main
from skeleton.application import (
    CAPABILITY_MANIFEST_VERSION,
    CODENAME_AUDIT_KIND,
    CONTRACT_VERSION_AUDIT_KIND,
    SESSION_MODE_AUDIT_KIND,
    TTL_AUDIT_KIND,
    capability_manifest,
    capability_view_audit_snapshot,
    codename_audit_snapshot,
    contract_version_audit_snapshot,
    get_codename_audit_row,
    get_contract_version_audit_row,
    get_session_mode_audit_row,
    get_ttl_audit_row,
    session_mode_audit_snapshot,
    ttl_audit_snapshot,
)


_SESSION_MODES = [
    "tutoring",
    "co_coding",
    "tactical",
    "builder",
    "cortex",
    "creative",
    "analytical",
    "debug",
]


def _assert_import_free(monkeypatch, snapshot, kind: str) -> None:
    called = False

    def should_not_import(_module_name: str):
        nonlocal called
        called = True
        raise AssertionError("audit must not import capability modules")

    monkeypatch.setattr("skeleton.application.capability_runtime.import_module", should_not_import)
    payload = snapshot()
    assert called is False
    assert payload["schema_version"] == CAPABILITY_MANIFEST_VERSION == 1
    assert payload["kind"] == kind


def _service():
    from skeleton.application import build_runtime_command_service

    class _State:
        genesis = None

        def is_healthy(self):
            return {"overall": True}

    return build_runtime_command_service(_State())


def test_idempotency_header_is_case_insensitive() -> None:
    from skeleton.api.idempotency import IDEMPOTENCY_HEADER, IdempotencyGuard

    assert IDEMPOTENCY_HEADER == "Idempotency-Key"
    guard = IdempotencyGuard()
    payload = {"status": "materialised"}
    guard.remember({"X-Idempotency-Key": "client-key-1"}, payload)
    assert guard.replay({"x-idempotency-key": "client-key-1"}) == payload
    assert guard.replay({"IDEMPOTENCY-KEY": "client-key-1"}) == payload
    assert guard.replay({IDEMPOTENCY_HEADER: "other"}) is None


def test_mint_seal_rejects_bool_ttl() -> None:
    from skeleton.api.hmac_seal import mint_seal

    with pytest.raises(ValueError, match="ttl_secs must be an integer"):
        mint_seal("alice", ttl_secs=True, secret="unit-test-seal-secret", now=1_700_000_000)
    with pytest.raises(ValueError, match="ttl_secs must be an integer"):
        mint_seal("alice", ttl_secs=60.0, secret="unit-test-seal-secret", now=1_700_000_000)


def test_rate_limiter_rejects_bool_capacity_refill_and_tokens() -> None:
    from skeleton.api.middleware import RateLimiter

    with pytest.raises(ValueError, match="capacity must be a positive finite number"):
        RateLimiter(capacity=True)
    with pytest.raises(ValueError, match="refill_per_sec must be a positive finite number"):
        RateLimiter(refill_per_sec=True)
    limiter = RateLimiter(capacity=2, refill_per_sec=1)
    with pytest.raises(ValueError, match="tokens must be finite"):
        limiter.check("client", tokens=True)


def test_bind_era_http_allow_lists_era_ids() -> None:
    import asyncio

    from fastapi import HTTPException

    from skeleton.api import routes
    from skeleton.forge.eras import list_eras

    class _Jeeves:
        def bind_era(self, era: str):
            return {"era": era, "primary_dps": 12}

    state = SimpleNamespace(jeeves=_Jeeves())
    bound = asyncio.run(routes.jeeves_bind_era({"era": "extraction_now"}, state=state))
    assert bound["era"] == "extraction_now"
    assert bound["status"] == "bound"
    defaulted = asyncio.run(routes.jeeves_bind_era({}, state=state))
    assert defaulted["era"] == "extraction_now"
    with pytest.raises(HTTPException) as extra:
        asyncio.run(routes.jeeves_bind_era({"era": "like elden ring"}, state=state))
    assert extra.value.status_code == 422
    assert "must be one of" in str(extra.value.detail)
    for era in list_eras():
        assert era in str(extra.value.detail)


def test_session_mode_audit_locks_core_llm_core_parity(monkeypatch) -> None:
    _assert_import_free(monkeypatch, session_mode_audit_snapshot, SESSION_MODE_AUDIT_KIND)
    payload = session_mode_audit_snapshot()
    assert payload["core"] == _SESSION_MODES
    assert payload["llm_core"] == _SESSION_MODES
    assert payload["values"] == _SESSION_MODES
    assert payload["drift"] == []
    assert payload["missing_from_core"] == []
    assert payload["missing_from_llm_core"] == []
    sources = [row["source"] for row in payload["modes"]]
    assert "skeleton.jeeves.core:SessionMode.TUTORING" in sources
    assert "skeleton.jeeves.llm_core:SessionMode.TUTORING" in sources


def test_codename_audit_locks_skeleton_identity(monkeypatch) -> None:
    _assert_import_free(monkeypatch, codename_audit_snapshot, CODENAME_AUDIT_KIND)
    payload = codename_audit_snapshot()
    assert payload["values"] == ["Skeleton"]
    assert payload["drift"] == []
    sources = [row["source"] for row in payload["codenames"]]
    assert "skeleton:__codename__" in sources
    assert "skeleton.architecture:CODENAME" in sources
    assert "skeleton.setup_config:CODENAME" in sources
    assert "skeleton.application.runtime_commands:configuration.application" in sources


def test_contract_version_audit_locks_1_0_identity(monkeypatch) -> None:
    _assert_import_free(monkeypatch, contract_version_audit_snapshot, CONTRACT_VERSION_AUDIT_KIND)
    payload = contract_version_audit_snapshot()
    assert payload["values"] == ["1.0"]
    assert payload["drift"] == []
    sources = [row["source"] for row in payload["versions"]]
    assert "skeleton.application.command_contracts:CONTRACT_VERSION" in sources


def test_ttl_audit_locks_300_second_identity(monkeypatch) -> None:
    _assert_import_free(monkeypatch, ttl_audit_snapshot, TTL_AUDIT_KIND)
    payload = ttl_audit_snapshot()
    assert payload["values"] == [300, 300.0, 300.0]
    assert payload["numbers"] == [300.0, 300.0, 300.0]
    assert payload["drift"] == []
    sources = [row["source"] for row in payload["ttls"]]
    assert "skeleton.api.hmac_seal:DEFAULT_TTL_SECS" in sources
    assert "skeleton.api.idempotency:IdempotencyEntry.ttl_seconds" in sources
    assert "skeleton.api.idempotency:IdempotencyGuard.default_ttl" in sources


def test_capability_view_flags_include_f60_audits() -> None:
    payload = capability_view_audit_snapshot()
    assert payload["missing_from_runtime"] == []
    assert payload["missing_from_cli"] == []
    assert payload["missing_from_help"] == []
    for flag in ("mode_audit", "codename_audit", "cver_audit", "ttl_audit"):
        assert flag in payload["runtime"]
        assert flag in payload["cli"]
        assert flag in payload["help"]


def test_cli_http_and_command_parity_for_f60_audits(capsys) -> None:
    import asyncio

    from fastapi import HTTPException

    from skeleton.api import routes

    pairs = [
        (["capabilities", "--mode-audit"], session_mode_audit_snapshot, routes.application_session_mode_audit, "mode_audit"),
        (["capabilities", "--codename-audit"], codename_audit_snapshot, routes.application_codename_audit, "codename_audit"),
        (["capabilities", "--cver-audit"], contract_version_audit_snapshot, routes.application_contract_version_audit, "cver_audit"),
        (["capabilities", "--ttl-audit"], ttl_audit_snapshot, routes.application_ttl_audit, "ttl_audit"),
    ]
    service = _service()
    identity = service.execute("capabilities")
    assert identity.to_payload()["data"] == capability_manifest()
    for argv, snapshot, http, flag in pairs:
        assert main(argv) == 0
        payload = snapshot()
        assert json.loads(capsys.readouterr().out) == payload
        assert asyncio.run(http()) == payload
        audit = service.execute("capabilities", {flag: True})
        assert audit.ok is True
        assert audit.to_payload()["data"] == payload
        invalid = service.execute("capabilities", {flag: 1})
        assert invalid.ok is False
        both = service.execute("capabilities", {flag: True, "token_audit": True})
        assert both.ok is False

    assert asyncio.run(
        routes.application_session_mode_audit_row("skeleton.jeeves.core:SessionMode.TUTORING")
    ) == get_session_mode_audit_row("skeleton.jeeves.core:SessionMode.TUTORING")
    assert asyncio.run(routes.application_codename_audit_row("skeleton:__codename__")) == get_codename_audit_row(
        "skeleton:__codename__"
    )
    assert asyncio.run(
        routes.application_contract_version_audit_row("skeleton.application.command_contracts:CONTRACT_VERSION")
    ) == get_contract_version_audit_row("skeleton.application.command_contracts:CONTRACT_VERSION")
    assert asyncio.run(
        routes.application_ttl_audit_row("skeleton.api.hmac_seal:DEFAULT_TTL_SECS")
    ) == get_ttl_audit_row("skeleton.api.hmac_seal:DEFAULT_TTL_SECS")
    with pytest.raises(HTTPException) as missing:
        asyncio.run(routes.application_ttl_audit_row("missing"))
    assert missing.value.status_code == 404
