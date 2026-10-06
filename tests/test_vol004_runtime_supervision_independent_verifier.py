from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_vol004_runtime_supervision import (
    EXPECTED_NETWORK_SURFACES,
    REQUIRED_SOURCE_KEYS,
    REQUIRED_VOL004_EVALUATIONS,
    REQUIRED_VOL004_TESTS,
    verify_repository,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _json(path: Path, value: object) -> None:
    _write(path, json.dumps(value))


def _valid_repo(tmp_path: Path) -> Path:
    root = tmp_path
    source_paths = {
        "runtime_manifest": "skeleton/app/manifest.json",
        "backend_server": "backend/server.py",
        "backend_engine_client": "backend/core/engine_client.py",
        "engine_server": "skeleton/api/server.py",
        "engine_runtime": "skeleton/api/engine_runtime.py",
        "engine_service": "skeleton/api/engine_service.py",
        "operation_runtime": "skeleton/persistence/operation_runtime.py",
        "shared_lifecycle": "skeleton/kernel/runtime_supervision.py",
        "governed_lifecycle_mirror": "skeleton/ai/runtime/kernel/runtime_supervision.py",
        "construction_contract": "machine/ai_app_construction.json",
    }
    assert set(source_paths) == REQUIRED_SOURCE_KEYS

    shared = "# RuntimeServiceLifecycle\n# RuntimeAdmissionMiddleware\n"
    _write(root / source_paths["shared_lifecycle"], shared)
    _write(root / source_paths["governed_lifecycle_mirror"], shared)

    binding_sources = {
        "backend/server.py": "# BACKEND_GUARD\n",
        "backend/core/engine_client.py": "# BACKEND_CANCEL\n",
        "skeleton/api/server.py": "# ENGINE_SERVER\n",
        "skeleton/api/engine_runtime.py": "# ENGINE_POISON\n",
        "skeleton/api/engine_service.py": "# ENGINE_SERVICE\n",
        "skeleton/persistence/operation_runtime.py": "# OPERATION_RUNTIME\n",
        "skeleton/provider_runtime.py": "# ENGINE_PROVIDER\n",
        "skeleton/automation/free_model.py": "# FREE_MODEL\n",
        "skeleton/automation/shift_supervisor/model_gateway.py": "# MODEL_GATEWAY\n",
        "skeleton/automation/chatgpt_adapter.py": "# CHATGPT_ADAPTER\n",
    }
    for relative, content in binding_sources.items():
        _write(root / relative, content)

    manifest = {
        "services": [
            {"name": "backend", "depends_on": ["mongo", "skeleton"]},
            {"name": "skeleton", "depends_on": ["mongo"]},
            {"name": "mongo", "depends_on": []},
        ]
    }
    _json(root / "skeleton/app/manifest.json", manifest)

    provider_surfaces = []
    owners = {
        "engine-runtime": ("skeleton/provider_runtime.py", "runtime_model"),
        "repository-automation": ("skeleton/automation/free_model.py", "automation_model"),
        "shift-supervisor-model-gateway": (
            "skeleton/automation/shift_supervisor/model_gateway.py",
            "automation_model",
        ),
        "repository-automation-chatgpt-adapter": (
            "skeleton/automation/chatgpt_adapter.py",
            "automation_model",
        ),
    }
    for surface_id in sorted(EXPECTED_NETWORK_SURFACES):
        owner, family = owners[surface_id]
        provider_surfaces.append(
            {
                "id": surface_id,
                "owner": owner,
                "family": family,
                "network_transport_owner": True,
            }
        )
    _json(
        root / "machine/ai_app_construction.json",
        {"provider_surfaces": provider_surfaces},
    )

    connector_rows = [
        {
            "id": "backend-engine",
            "owner": "backend/core/engine_client.py",
            "family": "internal_service",
            "cancellation_mode": "delegated_durable_cancel",
            "bounded_timeout": True,
            "retry_wait_cancellable": True,
            "late_result_fencing": True,
            "required_symbols": ["BACKEND_CANCEL"],
        }
    ]
    for surface in provider_surfaces:
        connector_rows.append(
            {
                "id": surface["id"],
                "surface_id": surface["id"],
                "owner": surface["owner"],
                "family": surface["family"],
                "cancellation_mode": "async_task_cancellation"
                if surface["id"] == "engine-runtime"
                else "bounded_blocking_token_fence",
                "bounded_timeout": True,
                "retry_wait_cancellable": True,
                "late_result_fencing": True,
                "required_symbols": [
                    {
                        "engine-runtime": "ENGINE_PROVIDER",
                        "repository-automation": "FREE_MODEL",
                        "shift-supervisor-model-gateway": "MODEL_GATEWAY",
                        "repository-automation-chatgpt-adapter": "CHATGPT_ADAPTER",
                    }[surface["id"]]
                ],
            }
        )

    qualification_gap = (
        "independent exact-head VOL-004 Runtime Supervision Closure "
        "qualification remains pending"
    )
    contract = {
        "schema_version": "skeleton.architecture.runtime_supervision.v2",
        "contract_version": "1.2.0",
        "status": "active",
        "masterplan_binding": {
            "volume_ref": "VOL-004",
            "title": "Kernel & Execution Foundation",
            "qualification_gap": qualification_gap,
            "retired_implementation_gaps": [
                "old gap one",
                "old gap two",
            ],
        },
        "sources": source_paths,
        "lifecycle_semantics": {
            "phases": ["starting", "ready", "draining", "stopped", "failed"],
            "work_admission_phase": "ready",
            "draining_revokes_admission": True,
            "restart_requires_terminal_generation": True,
            "restart_refreshes_cancellation_token": True,
            "monotonic_receipts": True,
            "work_leases": {
                "required": True,
                "generation_bound": True,
                "stop_requires_quiescence": True,
                "duplicate_work_id_policy": "deny",
                "stale_generation_release_policy": "deny",
                "shutdown_reconciliation": "synchronous_before_shutdown_returns",
                "task_identity_binding": True,
            },
            "public_drain_response": {
                "status_code": 503,
                "retry_after_seconds": 1,
                "forbidden_lifecycle_fields": [
                    "active_work_ids",
                    "cancellation",
                ],
            },
        },
        "connector_inventory": {
            "selection_rule": "network_transport_owner == true",
            "undeclared_connector_policy": "fail-closed",
            "extra_internal_connectors": ["backend-engine"],
        },
        "connectors": connector_rows,
        "services": [
            {
                "lifecycle_bindings": [
                    {
                        "path": "backend/server.py",
                        "required_symbols": ["BACKEND_GUARD"],
                    },
                    {
                        "path": "skeleton/api/engine_runtime.py",
                        "required_symbols": ["ENGINE_POISON"],
                    },
                ],
                "connector_bindings": [],
                "cancellation_bindings": [],
            }
        ],
    }
    _json(root / "machine/runtime_supervision.json", contract)

    master = {
        "volumes": [
            {
                "key": "VOL-004",
                "title": "Kernel & Execution Foundation",
                "implementation_status": "implemented",
                "tests": sorted(REQUIRED_VOL004_TESTS),
                "evaluations": sorted(REQUIRED_VOL004_EVALUATIONS),
                "gaps": [qualification_gap],
                "completion_checkbox": False,
                "completion_checkbox_mark": "[ ]",
                "enterprise_grade_state": "designed",
                "enterprise_grade_target": "superior",
            }
        ]
    }
    _json(root / "machine/ai_master_plan.json", master)
    return root


def test_independent_vol004_accepts_complete_contract(tmp_path: Path, monkeypatch) -> None:
    root = _valid_repo(tmp_path)
    monkeypatch.setenv("EVIDENCE_HEAD_SHA", "vol004-head")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "vol004-head"
    assert receipt["volume"] == "VOL-004"
    assert set(receipt["network_surface_ids"]) == EXPECTED_NETWORK_SURFACES
    assert set(receipt["connector_ids"]) == EXPECTED_NETWORK_SURFACES | {"backend-engine"}
    assert receipt["required_symbol_count"] == 7
    assert len(receipt["receipt_digest"]) == 64


def test_independent_vol004_rejects_mirror_drift(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    _write(
        root / "skeleton/ai/runtime/kernel/runtime_supervision.py",
        "# drift\n",
    )
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert "runtime supervision canonical/AI mirror drift" in receipt["errors"]


def test_independent_vol004_rejects_missing_network_surface(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["provider_surfaces"].pop()
    _json(path, payload)
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any("network transport surface identity drift" in e for e in receipt["errors"])


def test_independent_vol004_rejects_unbounded_connector(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/runtime_supervision.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["connectors"][0]["bounded_timeout"] = False
    _json(path, payload)
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any("bounded_timeout must remain true" in e for e in receipt["errors"])


def test_independent_vol004_rejects_missing_required_symbol(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    _write(root / "backend/server.py", "# guard removed\n")
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any("service binding required symbol missing" in e for e in receipt["errors"])


def test_independent_vol004_rejects_qualification_gap_drift(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_master_plan.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["volumes"][0]["gaps"] = ["different gap"]
    _json(path, payload)
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert "VOL-004 must retain exactly the contract qualification gap" in receipt["errors"]


def test_independent_vol004_rejects_missing_masterplan_evaluation(tmp_path: Path) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_master_plan.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["volumes"][0]["evaluations"].remove(
        "scripts/verify_vol004_runtime_supervision.py"
    )
    _json(path, payload)
    receipt = verify_repository(root)
    assert receipt["valid"] is False
    assert any("VOL-004 evaluation binding incomplete" in e for e in receipt["errors"])
