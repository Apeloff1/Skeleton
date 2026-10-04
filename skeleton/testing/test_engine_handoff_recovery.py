"""Read original accepted context identities across the authenticated boundary."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.core.engine_client import EngineContextBinding
from skeleton.api.engine_authority import EngineAuthorityRegistry, EngineServiceGrant
from skeleton.api.engine_service import (
    EngineExecutionService,
    SQLiteEngineSubmissionStore,
)
from skeleton.persistence.execution_repository import SQLiteExecutionRepository
from skeleton.testing.test_engine_routes import (
    _client,
    _inventory_headers,
    _service_and_command,
)


@pytest.fixture
def accepted(tmp_path):
    service, command = _service_and_command(tmp_path)
    service.submit(command, verified_service_principal="backend-service")
    try:
        yield service, command, _client(service)
    finally:
        service.repository.close()
        service.submissions.close()


def _get(client, *, execution_id="route-exec", actor_id="actor-a", tenant_id="tenant-a", headers=None):
    return client.get(
        f"/api/v1/engine/executions/{execution_id}/handoff",
        headers=_inventory_headers() if headers is None else headers,
        params={"actor_id": actor_id, "tenant_id": tenant_id},
    )


def _expected(command):
    operation = command.operation
    handoff = command.compiled_context
    return {
        "operation_id": operation.operation_id,
        "execution_id": command.execution_request.execution_id,
        "turn_id": handoff.turn_id,
        "tenant_id": operation.tenant_id,
        "actor_id": operation.actor_id,
        "context_id": handoff.context_id,
        "context_digest": handoff.context_digest,
        "compiler_version": handoff.compiler_version,
        "source_snapshot": [list(item) for item in handoff.source_snapshot],
        "data_class": handoff.data_class,
        "purpose": handoff.purpose,
        "handoff_digest": handoff.handoff_digest,
        "capability": operation.capability,
        "idempotency_key": operation.idempotency_key,
        "trace_id": operation.trace_id,
    }


def test_handoff_recovers_exact_accepted_identity_without_content_or_effects(accepted):
    service, command, client = accepted
    before = service.repository.get("route-exec")
    response = _get(client)
    assert response.status_code == 200
    assert response.json() == _expected(command)
    binding = EngineContextBinding.from_payload(
        response.json(),
        expected_execution_id="route-exec",
        expected_actor_id="actor-a",
        expected_tenant_id="tenant-a",
    )
    assert binding.context_digest == command.compiled_context.context_digest
    assert binding.handoff_digest == command.compiled_context.handoff_digest
    assert service.repository.get("route-exec") == before
    assert service.repository.latest_checkpoint("route-exec") is None
    assert service.repository.result("route-exec") is None
    assert command.compiled_context.instructions not in response.text
    assert command.compiled_context.prompt not in response.text
    assert not {"instructions", "prompt", "history", "tools", "delegated_authority"} & response.json().keys()


@pytest.mark.parametrize("header", ["authorization", "x-zaibatsu-attester"])
def test_handoff_requires_sealed_service_authentication(accepted, header):
    _service, _command, client = accepted
    headers = _inventory_headers()
    headers.pop(header)
    response = _get(client, headers=headers)
    assert response.status_code == 401
    assert "context_digest" not in response.json()


@pytest.mark.parametrize("field", ["actor_id", "tenant_id"])
def test_handoff_rejects_other_actor_or_tenant(accepted, field):
    _service, _command, client = accepted
    response = _get(client, **{field: "other"})
    assert response.status_code == 403
    assert "context_digest" not in response.json()


@pytest.mark.parametrize("change", ["principal", "scope", "tenant", "capability"])
def test_handoff_requires_original_principal_and_current_read_grant(accepted, change):
    service, _command, client = accepted
    principal = "other-service" if change == "principal" else "backend-service"
    service.authorities = EngineAuthorityRegistry(
        [
            EngineServiceGrant(
                service_principal=principal,
                scopes=frozenset({"engine:submit" if change == "scope" else "engine:read"}),
                tenant_ids=frozenset({"other" if change == "tenant" else "tenant-a"}),
                capabilities=frozenset({"other" if change == "capability" else "assistant.chat"}),
            )
        ]
    )
    headers = {**_inventory_headers(), "x-zaibatsu-attester": principal}
    response = _get(client, headers=headers)
    assert response.status_code == 403
    assert "context_digest" not in response.json()


def test_handoff_unknown_execution_and_missing_or_oversized_queries(accepted):
    _service, _command, client = accepted
    assert _get(client, execution_id="unknown-execution").status_code == 404
    assert _get(client, actor_id="x" * 513).status_code == 422
    assert (
        client.get("/api/v1/engine/executions/route-exec/handoff", headers=_inventory_headers()).status_code
        == 422
    )


def test_handoff_exact_identity_survives_durable_service_restart(tmp_path):
    service, command = _service_and_command(tmp_path)
    service.submit(command, verified_service_principal="backend-service")
    service.repository.checkpoint(
        "route-exec",
        {"context_digest": command.compiled_context.context_digest, "tenant_id": "tenant-a"},
        expected_execution_version=service.repository.get("route-exec").version,
        expected_checkpoint_version=0,
    )
    authority = service.authorities
    first = _get(_client(service)).json()
    service.repository.close()
    service.submissions.close()
    reopened = EngineExecutionService(
        SQLiteExecutionRepository(tmp_path / "execution.sqlite3"),
        SQLiteEngineSubmissionStore(tmp_path / "submission.sqlite3"),
        authority,
    )
    try:
        response = _get(_client(reopened))
        assert response.status_code == 200
        assert response.json() == first == _expected(command)
    finally:
        reopened.repository.close()
        reopened.submissions.close()


def test_handoff_historical_read_preserves_expired_delegation_semantics(tmp_path):
    service, command = _service_and_command(tmp_path)
    now = datetime.now(UTC)
    command = replace(
        command,
        operation=replace(
            command.operation, created_at=now - timedelta(minutes=2), deadline=now - timedelta(minutes=1)
        ),
        delegated_authority=replace(
            command.delegated_authority,
            issued_at=now - timedelta(minutes=2),
            expires_at=now - timedelta(minutes=1),
            authority_digest=None,
        ),
    )
    # Admission was valid at the original time; historical reads use current grants.
    service.submit(command, verified_service_principal="backend-service", now=now - timedelta(minutes=2))
    try:
        response = _get(_client(service))
        assert response.status_code == 200
        assert response.json() == _expected(command)
    finally:
        service.repository.close()
        service.submissions.close()


@pytest.mark.parametrize(
    "corruption",
    ["invalid_json", "content", "swapped_request", "ack", "missing_ack_identity", "trace", "state"],
)
def test_handoff_corrupt_durable_submission_or_execution_fails_closed(accepted, corruption):
    service, command, client = accepted
    db = service.submissions._connection
    if corruption == "state":
        service.repository._connection.execute(
            "UPDATE ai_execution_state SET identity_digest=? WHERE execution_id=?", ("0" * 64, "route-exec")
        )
    elif corruption in {"ack", "missing_ack_identity"}:
        ack = json.loads(db.execute("SELECT ack_json FROM engine_submission").fetchone()[0])
        if corruption == "ack":
            ack["execution_id"] = "other-execution"
        else:
            del ack["execution_id"]
        db.execute("UPDATE engine_submission SET ack_json=?", (json.dumps(ack),))
    else:
        payload = command.as_dict()
        if corruption == "content":
            payload["compiled_context"]["instructions"] = "corrupted private instruction"
        elif corruption == "swapped_request":
            payload["execution_request"]["objective"] = "independently valid substituted work"
        elif corruption == "trace":
            payload["operation"]["trace_id"] = "substituted-trace"
        encoded = "{" if corruption == "invalid_json" else json.dumps(payload)
        db.execute("UPDATE engine_submission SET command_json=?", (encoded,))
    response = _get(client)
    assert response.status_code == 422
    assert "context_digest" not in response.json()
    assert "corrupted private instruction" not in response.text
    assert service.repository.result("route-exec") is None


@pytest.mark.parametrize("field", ["context_digest", "tenant_id"])
def test_handoff_rejects_self_consistent_checkpoint_context_substitution(accepted, field):
    service, command, client = accepted
    payload = {"context_digest": command.compiled_context.context_digest, "tenant_id": "tenant-a"}
    payload[field] = "c" * 64 if field == "context_digest" else "other-tenant"
    # Store a structurally valid checkpoint with a genuine repository digest.
    service.repository.checkpoint(
        "route-exec",
        payload,
        expected_execution_version=service.repository.get("route-exec").version,
        expected_checkpoint_version=0,
    )
    response = _get(client)
    assert response.status_code == 422
    assert "context_digest" not in response.json()
