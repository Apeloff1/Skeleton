from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_provider_redundancy_closure import (
    REQUIRED_RUNTIME_TOKENS,
    REQUIRED_TEST_TOKENS,
    verify_repository,
)


def _valid_repo(tmp_path: Path) -> Path:
    runtime = tmp_path / "skeleton/provider_runtime.py"
    mirror = tmp_path / "skeleton/ai/runtime/provider_runtime.py"
    tests = tmp_path / "skeleton/testing/test_provider_contract.py"
    construction = tmp_path / "machine/ai_app_construction.json"

    runtime.parent.mkdir(parents=True, exist_ok=True)
    mirror.parent.mkdir(parents=True, exist_ok=True)
    tests.parent.mkdir(parents=True, exist_ok=True)
    construction.parent.mkdir(parents=True, exist_ok=True)

    runtime_source = "\n".join(REQUIRED_RUNTIME_TOKENS) + "\n"
    runtime.write_text(runtime_source, encoding="utf-8")
    mirror.write_text(runtime_source, encoding="utf-8")
    tests.write_text("\n".join(REQUIRED_TEST_TOKENS) + "\n", encoding="utf-8")

    payload = {
        "runtime_model_providers": [
            {
                "id": "openai-compatible-secondary",
                "state": "optional",
                "architecture_read_required": True,
                "construction_manual_read_required": True,
                "activation_receipt_required": True,
                "credentials": ["AI_SECONDARY_API_KEY"],
                "capabilities": ["text-generation"],
            }
        ],
        "provider_redundancy_blueprint": {
            "status": "closed",
            "gap": "gap-provider-redundancy",
            "routing": {
                "failover_on": [
                    "ProviderUnavailableError",
                    "ProviderInvocationError",
                ],
                "never_failover_on": [
                    "ProviderPolicyError",
                    "governance denial",
                    "admission denial",
                    "schema/protocol violation",
                    "explicit non-primary model mapping",
                ],
            },
        },
        "gap_register": [
            {
                "id": "gap-provider-redundancy",
                "status": "closed",
            }
        ],
    }
    construction.write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path


def test_provider_redundancy_verifier_accepts_complete_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _valid_repo(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "redundancy-head")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "redundancy-head"
    assert receipt["declared_secondary"] is True


def test_provider_redundancy_verifier_rejects_runtime_mirror_drift(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    mirror = root / "skeleton/ai/runtime/provider_runtime.py"
    mirror.write_text("# drift\n", encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("mirror drift" in error for error in receipt["errors"])


def test_provider_redundancy_verifier_rejects_policy_failover_loss(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["provider_redundancy_blueprint"]["routing"]["never_failover_on"] = [
        "governance denial"
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "provider policy denial is no longer fail-closed" in error
        for error in receipt["errors"]
    )


def test_provider_redundancy_verifier_rejects_secondary_capability_widening(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["runtime_model_providers"][0]["capabilities"] = [
        "text-generation",
        "image-generation",
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "capability declaration is not text-only" in error
        for error in receipt["errors"]
    )


def test_provider_redundancy_verifier_rejects_missing_outage_regression(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "skeleton/testing/test_provider_contract.py"
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        "test_failover_provider_routes_invocation_failure_to_secondary_model\n",
        "",
    )
    path.write_text(source, encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "provider tests lost redundancy token" in error
        for error in receipt["errors"]
    )



def test_provider_redundancy_verifier_rejects_missing_protocol_fence_regression(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "skeleton/testing/test_provider_contract.py"
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        "test_failover_provider_never_routes_protocol_violation\n",
        "",
    )
    path.write_text(source, encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "provider tests lost redundancy token" in error
        for error in receipt["errors"]
    )

def test_provider_redundancy_verifier_rejects_reopened_gap(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["gap_register"][0]["status"] = "open"
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("gap must remain closed" in error for error in receipt["errors"])


def test_provider_redundancy_verifier_rejects_blueprint_regression(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine/ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["provider_redundancy_blueprint"]["status"] = (
        "implemented-pending-closure"
    )
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("blueprint must remain closed" in error for error in receipt["errors"])

