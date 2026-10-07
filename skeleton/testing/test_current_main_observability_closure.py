"""Fail-closed lock for current-main observability and integration closure.

Issue #955 verifies already-implemented contracts on current main. This module
does not add a parallel observability stack. It fails when canonical evidence is
missing, and it refuses to treat queued, cancelled, or stale aggregate results
as success.

Verified 2026-09-18 against origin/main
``389ef25dd964ad0a2c6c5a1c915912dd3b8a76bf``:
Merge Readiness run 35283087096 concluded success. Quarantine Policy, Unit,
Integration Smoke, Lint Type Security, PR Automation Tests, and Merge Readiness
all succeeded. First failing job: none.
"""

from __future__ import annotations

from pathlib import Path

from skeleton.kernel.events import DomainEvent, EventBus
from skeleton.observability.redaction import REDACTED, redact_payload, redact_text

ROOT = Path(__file__).resolve().parents[2]
MERGE_READINESS = ROOT / ".github/workflows/merge-readiness.yml"
QUALITY_GATES = ROOT / "scripts/quality-gates.sh"
MERGE_READINESS_CONTRACT = ROOT / "scripts/check_merge_readiness_contract.py"

EVIDENCE_FILES = (
    MERGE_READINESS,
    QUALITY_GATES,
    MERGE_READINESS_CONTRACT,
    ROOT / "tests/test_cross_subsystem_integration.py",
    ROOT / "tests/test_frontier_runtime_memory_retrieval.py",
    ROOT / "tests/test_model_runtime.py",
    ROOT / "tests/test_observability.py",
    ROOT / "tests/test_runtime_observability_bridge.py",
    ROOT / "skeleton/testing/test_frontier_observability_correlation.py",
    ROOT / "skeleton/observability/redaction.py",
    Path(__file__),
)

INTEGRATION_SMOKE_TESTS = (
    "tests/test_cross_subsystem_integration.py",
    "tests/test_frontier_runtime_memory_retrieval.py",
    "tests/test_model_runtime.py",
    "skeleton/testing/test_frontier_observability_correlation.py",
)

QUALITY_OBSERVABILITY_TESTS = (
    "skeleton/testing/test_frontier_observability_correlation.py",
    "skeleton/testing/test_current_main_observability_closure.py",
    "tests/test_observability.py",
    "tests/test_runtime_observability_bridge.py",
)

API_RUNTIME_TOOL_STATE_MARKERS = (
    "def test_boundary_api_correlation__orchestrator__tool__state_happy_path",
    "def test_request_id_survives_api_to_run_to_tool_without_payload_leakage",
    "def test_tool_failure_event_exposes_type_not_secret_message",
    "def test_retry_event_is_correlated_and_does_not_store_exception_message",
    "run_with_request_correlation",
    "ObservableOrchestrator",
)

API_RETRIEVAL_RAG_PROVENANCE_MARKERS = (
    "def test_boundary_api__retrieval__rag__fusion__provenance_happy_path",
    "def test_boundary_api_gate__retrieval_state_rejects_invalid_seal_without_mutation",
    "def test_runtime_uses_retriever_contract_and_preserves_source_provenance",
    "def test_runtime_retrieval_fails_closed_without_source_provenance",
    'hit["plane"] == "rag"',
    'hit["provenance"] == (',
)

PROVIDER_STORAGE_TOOL_FAILURE_MARKERS = (
    "def test_runtime_retries_transient_failure_once",
    "def test_timeout_and_precancel_are_deterministic",
    "ProviderTimeoutError",
    "ProviderCancelledError",
    "def test_memory_backend_exception_message_is_not_exposed_or_persisted",
    "class _ExplodingMemory",
    "def test_tool_failure_event_exposes_type_not_secret_message",
    "TransientToolError",
)

REDACTION_MARKERS = (
    "def test_event_metrics_bridge_redacts_and_collects_baseline_metrics",
    "def test_structured_logger_redacts_messages_and_context",
    'assert first["payload"]["authorization"] == "[REDACTED]"',
    'assert event.context["password"] == "[REDACTED]"',
    "def test_request_id_survives_api_to_run_to_tool_without_payload_leakage",
    'assert "do-not-log" not in rendered',
)

NON_SUCCESS_RESULTS = (
    "queued",
    "cancelled",
    "skipped",
    "failure",
    "stale",
    "neutral",
    "timed_out",
    "action_required",
    "",
)


def _read(path: Path) -> str:
    if not path.is_file():
        raise AssertionError(f"missing evidence file: {path.relative_to(ROOT)}")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AssertionError(f"unreadable evidence file {path.relative_to(ROOT)}: {exc}") from exc


def _missing_markers(text: str, markers: tuple[str, ...], *, evidence: str) -> list[str]:
    return [f"{evidence}: {marker}" for marker in markers if marker not in text]


def test_canonical_evidence_files_exist() -> None:
    missing = [str(path.relative_to(ROOT)) for path in EVIDENCE_FILES if not path.is_file()]
    if missing:
        raise AssertionError(
            "current-main observability closure missing evidence files:\n"
            + "\n".join(f"  - {path}" for path in missing)
        )


def test_merge_readiness_and_integration_smoke_remain_fail_closed() -> None:
    workflow = _read(MERGE_READINESS)
    contract = _read(MERGE_READINESS_CONTRACT)
    missing = _missing_markers(
        workflow,
        (
            "name: Merge Readiness",
            "name: Integration Smoke",
            'result != "success"',
            "cancel-in-progress: ${{ github.event_name == 'pull_request' }}",
            "group: merge-readiness-${{ github.event.pull_request.number || github.sha }}",
        ),
        evidence=".github/workflows/merge-readiness.yml",
    )
    missing.extend(
        _missing_markers(
            contract,
            (
                'result != "success"',
                "Merge Readiness must fail on every non-success result",
                "unconditional merge-readiness cancellation can erase canonical main verification evidence",
            ),
            evidence="scripts/check_merge_readiness_contract.py",
        )
    )
    if "cancel-in-progress: true" in workflow:
        missing.append(
            ".github/workflows/merge-readiness.yml: unconditional cancel-in-progress: true"
        )
    if missing:
        raise AssertionError(
            "current-main merge-readiness closure missing evidence:\n"
            + "\n".join(f"  - {item}" for item in missing)
        )

    ready = {
        "quarantine_policy": "success",
        "unit": "success",
        "integration_smoke": "success",
        "quality_security": "success",
        "pr_automation": "success",
    }
    assert all(result == "success" for result in ready.values())
    for status in NON_SUCCESS_RESULTS:
        if status == "success":
            raise AssertionError("queued/cancelled/stale lock treated success as non-success")
        blocked = dict(ready)
        blocked["integration_smoke"] = status
        assert any(result != "success" for result in blocked.values())


def test_integration_smoke_runs_observability_and_boundary_matrix() -> None:
    workflow = _read(MERGE_READINESS)
    quality = _read(QUALITY_GATES)
    missing = [
        f".github/workflows/merge-readiness.yml: {path}"
        for path in INTEGRATION_SMOKE_TESTS
        if path not in workflow
    ]
    missing.extend(
        f"scripts/quality-gates.sh: {path}"
        for path in QUALITY_OBSERVABILITY_TESTS
        if path not in quality
    )
    if missing:
        raise AssertionError(
            "current-main integration/observability jobs missing evidence tests:\n"
            + "\n".join(f"  - {item}" for item in missing)
        )


def test_api_runtime_tool_state_and_retrieval_rag_provenance_paths() -> None:
    matrix = _read(ROOT / "tests/test_cross_subsystem_integration.py")
    retrieval = _read(ROOT / "tests/test_frontier_runtime_memory_retrieval.py")
    correlation = _read(ROOT / "skeleton/testing/test_frontier_observability_correlation.py")
    combined = f"{matrix}\n{retrieval}\n{correlation}"
    missing = _missing_markers(
        combined,
        API_RUNTIME_TOOL_STATE_MARKERS + API_RETRIEVAL_RAG_PROVENANCE_MARKERS,
        evidence="canonical boundary tests",
    )
    if missing:
        raise AssertionError(
            "current-main API/runtime/retrieval closure missing evidence:\n"
            + "\n".join(f"  - {item}" for item in missing)
        )


def test_correlation_survives_boundaries_and_redaction_is_enforced() -> None:
    observability = _read(ROOT / "tests/test_observability.py")
    bridge = _read(ROOT / "tests/test_runtime_observability_bridge.py")
    correlation = _read(ROOT / "skeleton/testing/test_frontier_observability_correlation.py")
    redaction = _read(ROOT / "skeleton/observability/redaction.py")
    combined = f"{observability}\n{bridge}\n{correlation}\n{redaction}"
    missing = _missing_markers(
        combined,
        REDACTION_MARKERS
        + (
            "def test_event_bus_emit_preserves_and_infers_correlation_id",
            "def test_journaled_bus_preserves_correlation_and_emits_baseline_metrics",
            '"authorization"',
            '"password"',
            '"api_key"',
            "REDACTED = \"[REDACTED]\"",
        ),
        evidence="correlation/redaction tests",
    )
    if missing:
        raise AssertionError(
            "current-main correlation/redaction closure missing evidence:\n"
            + "\n".join(f"  - {item}" for item in missing)
        )

    payload = redact_payload(
        {
            "authorization": "Bearer fixture-token",
            "password": "do-not-log",
            "api_key": "fixture-key",
            "ok": True,
            "error": "provider failed token=super-secret",
        }
    )
    assert payload["authorization"] == REDACTED
    assert payload["password"] == REDACTED
    assert payload["api_key"] == REDACTED
    assert payload["ok"] is True
    assert payload["error"] == "provider failed token=[REDACTED]"
    assert "fixture-token" not in repr(payload)
    assert "do-not-log" not in repr(payload)
    assert "fixture-key" not in repr(payload)
    assert "super-secret" not in repr(payload)
    assert redact_text("authorization=Basic abcdef") == "authorization=[REDACTED]"

    events: list[DomainEvent] = []
    bus = EventBus()
    bus.subscribe("runtime.*", events.append)
    bus.emit(
        "runtime.run.started",
        {"run_id": "run-closure"},
        correlation_id="req-closure-955",
    )
    bus.emit("runtime.agent.assigned", {"task_id": "task-closure"})
    bus.emit("runtime.tool.started", {"call_id": "call-closure"})
    assert [event.correlation_id for event in events] == [
        "req-closure-955",
        "task-closure",
        "call-closure",
    ]


def test_provider_storage_and_tool_failure_fixtures_remain_deterministic() -> None:
    model_runtime = _read(ROOT / "tests/test_model_runtime.py")
    memory = _read(ROOT / "tests/test_frontier_runtime_memory_retrieval.py")
    correlation = _read(ROOT / "skeleton/testing/test_frontier_observability_correlation.py")
    combined = f"{model_runtime}\n{memory}\n{correlation}"
    missing = _missing_markers(
        combined,
        PROVIDER_STORAGE_TOOL_FAILURE_MARKERS,
        evidence="deterministic failure fixtures",
    )
    if missing:
        raise AssertionError(
            "current-main provider/storage/tool failure closure missing evidence:\n"
            + "\n".join(f"  - {item}" for item in missing)
        )


def test_missing_evidence_fails_closed_instead_of_passing() -> None:
    missing = _missing_markers("present-only", ("present-only", "absent-claim"), evidence="fixture")
    assert missing == ["fixture: absent-claim"]
    try:
        _read(ROOT / "skeleton/testing/does-not-exist-observability-closure.py")
    except AssertionError as exc:
        assert "missing evidence file" in str(exc)
    else:
        raise AssertionError("missing evidence file was treated as success")

