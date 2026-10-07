from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_vol004_runtime_supervision import (
    QUALIFICATION_GAP,
    REQUIRED_VOL004_EVALUATIONS,
    REQUIRED_VOL004_PATHS,
    REQUIRED_VOL004_TESTS,
    verify_repository,
)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _valid_repo(tmp_path: Path) -> Path:
    root = tmp_path

    lifecycle_source = """
class RuntimeServiceLifecycle: pass
class WorkLease: pass
def acquire_work(): pass
def release_work(): pass
"""
    _write(root / "skeleton/kernel/runtime_supervision.py", lifecycle_source)
    _write(root / "skeleton/ai/runtime/kernel/runtime_supervision.py", lifecycle_source)

    binding_files = {
        "backend/server.py": [
            'RuntimeServiceLifecycle("backend")',
            "backend lifespan cannot overlap an active lifecycle generation",
        ],
        "backend/core/engine_client.py": ["cancel_execution"],
        "skeleton/api/server.py": ['RuntimeServiceLifecycle("skeleton")'],
        "skeleton/api/engine_runtime.py": [
            "self.lifecycle.acquire_work(",
            "self.lifecycle.release_work(lease)",
            "def _record_supervision_fault(",
            "engine execution coordinator supervision is faulted",
            "def supervision_snapshot(",
            "engine execution coordinator shutdown supervision failed",
        ],
        "skeleton/persistence/operation_runtime.py": ["deadline"],
        "skeleton/api/engine_service.py": ["cancel"],
        "skeleton/provider_runtime.py": ["deadline", "Cancellation"],
        "skeleton/automation/free_model.py": ["cancellation"],
        "skeleton/automation/shift_supervisor/model_gateway.py": ["cancellation"],
        "skeleton/automation/chatgpt_adapter.py": ["cancellation"],
    }
    for relative, symbols in binding_files.items():
        _write(root / relative, "\n".join(symbols) + "\n")

    _write(root / "scripts/check_architecture_runtime_supervision.py", "# canonical\n")
    _write(root / "docs/architecture/RUNTIME_SUPERVISION.md", "# runtime supervision\n")
    _write(root / ".github/workflows/vol004-runtime-supervision.yml", "name: test\n")
    _write(root / "tests/test_architecture_runtime_supervision.py", "# tests\n")
    _write(root / "skeleton/testing/test_vol004_runtime_supervision_v2.py", "# tests\n")
    _write(root / "skeleton/testing/test_kernel_supervisor_cancellation.py", "# tests\n")
    _write(root / "tests/test_vol004_runtime_supervision_independent.py", "# tests\n")

    contract = {
        "schema_version": "skeleton.architecture.runtime_supervision.v2",
        "contract_version": "1.2.0",
        "status": "active",
        "masterplan_binding": {
            "volume_ref": "VOL-004",
            "title": "Kernel & Execution Foundation",
            "implementation_state": "implemented_verification_pending",
            "qualification_gap": QUALIFICATION_GAP,
        },
        "sources": {
            "shared_lifecycle": "skeleton/kernel/runtime_supervision.py",
            "governed_lifecycle_mirror": "skeleton/ai/runtime/kernel/runtime_supervision.py",
        },
        "lifecycle_semantics": {
            "phases": ["starting", "ready", "draining", "stopped", "failed"],
            "work_admission_phase": "ready",
            "draining_revokes_admission": True,
            "terminal_phases": ["stopped", "failed"],
            "restart_requires_terminal_generation": True,
            "restart_refreshes_cancellation_token": True,
            "monotonic_receipts": True,
            "work_leases": {
                "required": True,
                "generation_bound": True,
                "duplicate_work_id_policy": "deny",
                "stale_generation_release_policy": "deny",
                "stop_requires_quiescence": True,
                "startup_recovery_exception": "engine durable recovery only",
                "shutdown_reconciliation": "synchronous_before_shutdown_returns",
                "task_identity_binding": True,
            },
            "public_drain_response": {
                "status_code": 503,
                "retry_after_seconds": 1,
                "forbidden_lifecycle_fields": ["active_work_ids", "cancellation"],
            },
        },
        "services": [
            {
                "service": "backend",
                "expected_dependencies": ["mongo", "skeleton"],
                "lifecycle_bindings": [
                    {
                        "path": "backend/server.py",
                        "required_symbols": binding_files["backend/server.py"],
                    }
                ],
                "connector_bindings": [
                    {
                        "path": "backend/core/engine_client.py",
                        "required_symbols": binding_files["backend/core/engine_client.py"],
                    }
                ],
            },
            {
                "service": "skeleton",
                "expected_dependencies": ["mongo"],
                "lifecycle_bindings": [
                    {
                        "path": "skeleton/api/server.py",
                        "required_symbols": binding_files["skeleton/api/server.py"],
                    },
                    {
                        "path": "skeleton/api/engine_runtime.py",
                        "required_symbols": binding_files["skeleton/api/engine_runtime.py"],
                    },
                    {
                        "path": "skeleton/persistence/operation_runtime.py",
                        "required_symbols": binding_files["skeleton/persistence/operation_runtime.py"],
                    },
                ],
                "cancellation_bindings": [
                    {
                        "path": "skeleton/api/engine_service.py",
                        "required_symbols": binding_files["skeleton/api/engine_service.py"],
                    }
                ],
            },
        ],
        "connectors": [
            {
                "id": "backend-engine",
                "owner": "backend/core/engine_client.py",
                "cancellation_mode": "delegated_durable_cancel",
                "bounded_timeout": True,
                "deadline_propagation": True,
                "retry_wait_cancellable": True,
                "late_result_fencing": True,
                "required_symbols": binding_files["backend/core/engine_client.py"],
            },
            {
                "id": "engine-runtime",
                "owner": "skeleton/provider_runtime.py",
                "surface_id": "engine-runtime",
                "family": "runtime_model",
                "cancellation_mode": "async_task_cancellation",
                "bounded_timeout": True,
                "deadline_propagation": True,
                "retry_wait_cancellable": True,
                "late_result_fencing": True,
                "required_symbols": binding_files["skeleton/provider_runtime.py"],
            },
            {
                "id": "repository-automation",
                "owner": "skeleton/automation/free_model.py",
                "surface_id": "repository-automation",
                "family": "automation_model",
                "cancellation_mode": "bounded_blocking_token_fence",
                "bounded_timeout": True,
                "deadline_propagation": False,
                "retry_wait_cancellable": True,
                "late_result_fencing": True,
                "required_symbols": binding_files["skeleton/automation/free_model.py"],
            },
            {
                "id": "shift-supervisor-model-gateway",
                "owner": "skeleton/automation/shift_supervisor/model_gateway.py",
                "surface_id": "shift-supervisor-model-gateway",
                "family": "automation_model",
                "cancellation_mode": "bounded_blocking_token_fence",
                "bounded_timeout": True,
                "deadline_propagation": False,
                "retry_wait_cancellable": True,
                "late_result_fencing": True,
                "required_symbols": binding_files[
                    "skeleton/automation/shift_supervisor/model_gateway.py"
                ],
            },
            {
                "id": "repository-automation-chatgpt-adapter",
                "owner": "skeleton/automation/chatgpt_adapter.py",
                "surface_id": "repository-automation-chatgpt-adapter",
                "family": "automation_model",
                "cancellation_mode": "bounded_blocking_token_fence",
                "bounded_timeout": True,
                "deadline_propagation": False,
                "retry_wait_cancellable": True,
                "late_result_fencing": True,
                "required_symbols": binding_files["skeleton/automation/chatgpt_adapter.py"],
            },
        ],
    }
    _write_json(root / "machine/runtime_supervision.json", contract)

    construction = {
        "provider_surfaces": [
            {
                "id": "engine-runtime",
                "owner": "skeleton/provider_runtime.py",
                "family": "runtime_model",
                "network_transport_owner": True,
            },
            {
                "id": "repository-automation",
                "owner": "skeleton/automation/free_model.py",
                "family": "automation_model",
                "network_transport_owner": True,
            },
            {
                "id": "shift-supervisor-model-gateway",
                "owner": "skeleton/automation/shift_supervisor/model_gateway.py",
                "family": "automation_model",
                "network_transport_owner": True,
            },
            {
                "id": "repository-automation-chatgpt-adapter",
                "owner": "skeleton/automation/chatgpt_adapter.py",
                "family": "automation_model",
                "network_transport_owner": True,
            },
        ]
    }
    _write_json(root / "machine/ai_app_construction.json", construction)

    manifest = {
        "services": [
            {"name": "backend", "depends_on": ["mongo", "skeleton"]},
            {"name": "skeleton", "depends_on": ["mongo"]},
            {"name": "mongo", "depends_on": []},
        ]
    }
    _write_json(root / "skeleton/app/manifest.json", manifest)

    master = {
        "volumes": [
            {
                "key": "VOL-004",
                "title": "Kernel & Execution Foundation",
                "scope": "canonical-plan",
                "implementation_status": "implemented",
                "requirements": [
                    "Bootstrap services in deterministic dependency order with explicit readiness and shutdown semantics.",
                    "Propagate cancellation, deadline, budget and operation identity through all runtime layers.",
                    "Prevent orphan work and unbounded background execution after terminal operation state.",
                ],
                "implementation_paths": sorted(REQUIRED_VOL004_PATHS),
                "tests": sorted(REQUIRED_VOL004_TESTS),
                "evaluations": sorted(REQUIRED_VOL004_EVALUATIONS),
                "gaps": [QUALIFICATION_GAP],
                "completion_checkbox": False,
                "completion_checkbox_mark": "[ ]",
                "enterprise_grade_state": "designed",
                "enterprise_grade_target": "superior",
            }
        ]
    }
    _write_json(root / "machine/ai_master_plan.json", master)
    return root


def test_independent_verifier_accepts_closed_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _valid_repo(tmp_path)
    monkeypatch.setenv("EVIDENCE_HEAD_SHA", "vol004-head")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "vol004-head"
    assert receipt["volume"] == "VOL-004"
    assert len(receipt["connector_digests"]) == 5
    assert len(receipt["receipt_digest"]) == 64


def test_independent_verifier_rejects_lifecycle_mirror_drift(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    mirror = root / "skeleton/ai/runtime/kernel/runtime_supervision.py"
    mirror.write_text("# drift\n", encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert "runtime lifecycle governed mirror drifted" in receipt["errors"]


def test_independent_verifier_rejects_missing_required_symbol(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    path = root / "backend/server.py"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "backend lifespan cannot overlap an active lifecycle generation",
            "",
        ),
        encoding="utf-8",
    )

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "backend/server.py missing required runtime symbol" in error
        for error in receipt["errors"]
    )


def test_independent_verifier_rejects_connector_coverage_drift(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/runtime_supervision.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["connectors"] = [
        row for row in payload["connectors"]
        if row["id"] != "repository-automation"
    ]
    _write_json(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("network connector coverage mismatch" in error for error in receipt["errors"])


def test_independent_verifier_rejects_unbounded_connector(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/runtime_supervision.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["connectors"][0]["bounded_timeout"] = False
    _write_json(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("must have bounded timeout" in error for error in receipt["errors"])


def test_independent_verifier_rejects_runtime_dependency_drift(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    path = root / "skeleton/app/manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["services"][0]["depends_on"] = ["mongo"]
    _write_json(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert "runtime dependency drift for service backend" in receipt["errors"]


def test_independent_verifier_rejects_masterplan_binding_loss(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_master_plan.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["volumes"][0]["evaluations"].remove(
        "scripts/verify_vol004_runtime_supervision.py"
    )
    _write_json(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "VOL-004 evaluation binding incomplete" in error
        for error in receipt["errors"]
    )


def test_independent_verifier_rejects_unexpected_gap_state(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_master_plan.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["volumes"][0]["gaps"].append("new implementation gap")
    _write_json(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert "VOL-004 gap state contains unexpected obligations" in receipt["errors"]


def test_independent_verifier_accepts_signed_closure_state(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    contract_path = root / "machine/runtime_supervision.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["masterplan_binding"]["implementation_state"] = "verified"
    _write_json(contract_path, contract)

    master_path = root / "machine/ai_master_plan.json"
    master = json.loads(master_path.read_text(encoding="utf-8"))
    volume = next(v for v in master["volumes"] if v["key"] == "VOL-004")
    volume["gaps"] = []
    volume["completion_checkbox"] = True
    volume["completion_checkbox_mark"] = "[x]"
    volume["implementation_status"] = "verified"
    _write_json(master_path, master)

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []


def test_independent_verifier_rejects_signed_pending_machine_state(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    master_path = root / "machine/ai_master_plan.json"
    master = json.loads(master_path.read_text(encoding="utf-8"))
    volume = next(v for v in master["volumes"] if v["key"] == "VOL-004")
    volume["gaps"] = []
    volume["completion_checkbox"] = True
    volume["completion_checkbox_mark"] = "[x]"
    volume["implementation_status"] = "verified"
    _write_json(master_path, master)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "implementation_state/masterplan drift" in error
        for error in receipt["errors"]
    )


def test_independent_verifier_rejects_requirement_drift(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_master_plan.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    volume = next(v for v in payload["volumes"] if v["key"] == "VOL-004")
    volume["requirements"] = [
        value
        for value in volume["requirements"]
        if "Prevent orphan work" not in value
    ]
    _write_json(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "VOL-004 requirement invariant lost" in error
        for error in receipt["errors"]
    )


def test_independent_verifier_rejects_scope_drift(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_master_plan.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    volume = next(v for v in payload["volumes"] if v["key"] == "VOL-004")
    volume["scope"] = "shadow-plan"
    _write_json(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert "VOL-004 scope drifted" in receipt["errors"]
