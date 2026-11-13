"""No live database: reject telemetry request flooding before JSON decode."""
from __future__ import annotations

import json

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from routes.telemetry import (
    CrashReport,
    TelemetryBatch,
    TelemetryEvent,
    _BoundedTelemetryRoute,
    _MAX_TELEMETRY_BATCH,
    _MAX_TELEMETRY_BODY_BYTES,
    _norm,
)


def _item(**overrides):
    return {
        "modal_id": "Editor",
        "session_id": "s_opaque",
        "event": "open",
        "severity": "info",
        **overrides,
    }


@pytest.fixture
def guarded_client():
    app = FastAPI()
    router = APIRouter(route_class=_BoundedTelemetryRoute)

    @router.post("/admit")
    async def admit(batch: TelemetryBatch):
        return {"received": len(batch.events)}

    app.include_router(router)
    return TestClient(app)


def test_small_request_reaches_normal_fastapi_parser(guarded_client):
    response = guarded_client.post("/admit", json={"events": [_item()]})
    assert response.status_code == 200
    assert response.json() == {"received": 1}


def test_server_admits_up_to_but_not_more_than_100_events(guarded_client):
    assert _MAX_TELEMETRY_BATCH == 100
    allowed = guarded_client.post(
        "/admit", json={"events": [_item()] * _MAX_TELEMETRY_BATCH}
    )
    assert allowed.status_code == 200
    assert allowed.json()["received"] == 100
    denied = guarded_client.post("/admit", json={
        "events": [_item()] * (_MAX_TELEMETRY_BATCH + 1)
    })
    assert denied.status_code == 422


def test_oversize_body_fails_before_model_validation(guarded_client):
    oversized = {
        "events": [_item(detail={"payload": "X" * _MAX_TELEMETRY_BODY_BYTES})]
    }
    response = guarded_client.post("/admit", json=oversized)
    assert response.status_code == 413
    assert "payload" not in response.text


def test_spoofed_short_content_length_does_not_bypass_body_budget(guarded_client):
    oversized = json.dumps({
        "events": [_item(detail={"payload": "Y" * _MAX_TELEMETRY_BODY_BYTES})]
    })
    response = guarded_client.post(
        "/admit", content=oversized,
        headers={"content-type": "application/json", "content-length": "1"},
    )
    assert response.status_code == 413


@pytest.mark.parametrize("body", [
    {"events": []},
    {"events": [_item(session_id="")]},
    {"events": [_item(modal_id="x" * 81)]},
    {"events": [_item(event="x" * 65)]},
    {"events": [_item(severity="critical")]},
    {"events": [_item(ts_client=-1)]},
    {"events": [_item(duration_ms=-1)]},
    {"events": [_item(duration_ms=86_400_001)]},
])
def test_bounded_and_typed_batch_schema_rejects_abuse(body):
    with pytest.raises(ValidationError):
        TelemetryBatch.model_validate(body)


def test_negative_and_nonfinite_telemetry_numbers_are_rejected():
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValidationError):
            TelemetryEvent.model_validate(_item(ts_client=bad))
        with pytest.raises(ValidationError):
            TelemetryEvent.model_validate(_item(duration_ms=bad))


def test_crash_report_is_bounded_before_detail_redaction():
    with pytest.raises(ValidationError):
        CrashReport.model_validate({"message": "x" * 2001})
    with pytest.raises(ValidationError):
        CrashReport.model_validate({
            "message": "safe", "stack": "x" * 16_385,
        })


def test_server_side_minimum_necessary_telemetry_drops_private_detail():
    event = TelemetryEvent.model_validate(_item(
        detail={
            "authorization": "Bearer private-secret",
            "safe": {"password": "private-secret"},
        },
    ))
    result = _norm(event)
    assert "private-secret" not in json.dumps(result)
    # Sensitive keys and nested objects are dropped rather than stored as
    # redacted-looking placeholders; raw text must never reach persistence.
    assert result["detail"] is None
