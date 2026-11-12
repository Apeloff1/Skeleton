"""Adversarial data-minimization tests for the server telemetry boundary."""

from __future__ import annotations

import json
import math

import pytest
from pydantic import ValidationError

from core.telemetry_privacy import (
    crash_metadata,
    safe_detail,
    safe_event,
    safe_label,
    safe_number,
    safe_session,
)
from routes.telemetry import CrashReport, TelemetryBatch, TelemetryEvent, _norm, crash_row


def _event(**kwargs):
    return TelemetryEvent(
        modal_id="ToolsArena",
        session_id="s_12345678-1234-4234-9234-123456789abc",
        event="action:packageBuild",
        severity="error",
        detail={
            "status": "failed",
            "count": 2,
            "password": "long-secret-not-for-telemetry",
            "access_token": "Bearer secret-exfiltration",
            "stack": "/var/private/api-key/stack",
            "message": "database://user:password@example.test",
            "freeform": "private user prompt",
            "payload": {"authentication": "secret"},
            "duration": 0.5,
        },
        **kwargs,
    )


def test_minimal_diagnostic_fields_survive_without_exfiltrating_strings():
    row = _norm(_event())
    assert row["modal_id"] == "ToolsArena"
    assert row["session_id"].startswith("s_")
    assert row["event"] == "action:packageBuild"
    assert row["severity"] == "error"
    assert row["detail"] == {
        "status": "failed", "count": 2.0, "duration": 0.5,
    }
    serialized = json.dumps(row)
    for secret in ("secret", "password", "Bearer", "/var/private", "private user prompt"):
        assert secret not in serialized


def test_untrusted_identifiers_cannot_become_url_or_credential_records():
    event = TelemetryEvent(
        modal_id="https://token@private.invalid/foo",
        session_id="Authorization: Bearer secret",
        event="action:hello?token=secret",
        severity="info",
        detail={"status": "private_secret", "ok": True},
    )
    row = _norm(event)
    assert row["modal_id"] == "unknown"
    assert row["session_id"] == "unknown"
    assert row["event"] == "other"
    assert row["severity"] == "info"
    assert row["detail"] == {"ok": True}
    # The admission model must reject unknown severities before persistence.
    with pytest.raises(ValidationError):
        TelemetryEvent(
            modal_id="ToolsArena", session_id="s_opaque",
            event="open", severity="rotating_secret",
        )


@pytest.mark.parametrize("value", [
    None, float("nan"), float("inf"), -1, 1_000_000_001, True,
    "99999999", object(),
])
def test_nonfinite_or_invalid_numbers_are_dropped(value):
    assert safe_number(value, maximum=1_000_000_000) is None


def test_bounded_detail_does_not_walk_nesting_or_sensitive_keys():
    cyclic = {}
    cyclic["self"] = cyclic
    raw = {
        "safe": True,
        "mode": "offline",
        "state": "running",
        "error_type": "TypeError",
        "data": cyclic,
        "url": "https://user:secret@internal.invalid",
        "message": "do not log me",
        "score": math.inf,
    }
    assert safe_detail(raw) == {
        "safe": True, "mode": "offline",
        "state": "running", "error_type": "TypeError",
    }
    assert safe_detail([raw]) is None
    assert safe_detail("password=secret") is None


def test_crash_diagnostics_never_persist_stack_message_or_info_text():
    report = CrashReport(
        source="https://internal.invalid/?access_token=secret",
        component="PasswordModal",
        message="login secret=private user text",
        stack="private/file/line 2 Authorization: Bearer xyz",
        session_id="session_contains_api_key",
        app_version="private-data",
        info={"password": "abc", "count": 1, "status": "failed"},
    )
    row = crash_row(report)
    assert row["event"] == "crash"
    assert row["session_id"] == "unknown"
    assert row["detail"]["stack_present"] is True
    assert row["detail"]["message_present"] is True
    assert row["detail"]["info"] == {"count": 1.0, "status": "failed"}
    serialized = json.dumps(row)
    for secret in ("Authorization", "PasswordModal", "private-data", "Bearer", "abc", "secret"):
        assert secret not in serialized


def test_too_large_batch_and_oversized_fields_are_rejected_early():
    event = _event()
    with pytest.raises(ValidationError):
        TelemetryBatch(events=[event] * 101)
    with pytest.raises(ValidationError):
        TelemetryEvent(modal_id="x" * 81, session_id="s", event="open")
    with pytest.raises(ValidationError):
        CrashReport(message="x" * 4097)


def test_backend_helper_allowlists_are_narrow():
    assert safe_label("ToolsArena") == "ToolsArena"
    assert safe_label("a?credential=secret") == "unknown"
    assert safe_event("action:compile") == "action:compile"
    assert safe_event("action:compile?token=secret") == "other"
    assert safe_session("s_12345678-1234-4234-9234-123456789abc").startswith("s_")
    assert safe_session("s_1234") == "unknown"
    metadata = crash_metadata(
        source="secret", component="secret", message="secret", stack="secret",
        info={"auth": "secret"}, app_version="secret",
    )
    assert "secret" not in json.dumps(metadata)
