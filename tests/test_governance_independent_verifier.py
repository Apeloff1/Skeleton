from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_governance_closure import (
    BOUNDARIES,
    MIRROR_PAIRS,
    REQUIRED_CROSS_PLANE_BINDINGS,
    REQUIRED_DECISIONS,
    REQUIRED_FAIL_CLOSED_PHRASES,
    verify_repository,
)


def _write_machine_contract(root: Path) -> None:
    machine = root / "machine"
    machine.mkdir(parents=True, exist_ok=True)
    construction = {
        "gap_register": [
            {
                "id": "gap-governance-registry",
                "status": "open",
            }
        ],
        "governance_runtime_blueprint": {
            "canonical_owner": "skeleton/vault",
            "decisions": sorted(REQUIRED_DECISIONS),
            "cross_plane_bindings": sorted(REQUIRED_CROSS_PLANE_BINDINGS),
            "fail_closed": list(REQUIRED_FAIL_CLOSED_PHRASES),
            "decision_receipt": {
                "required_fields": [
                    "decision_id",
                    "operation_id",
                    "tenant_id",
                    "action",
                    "resource_refs",
                    "allowed",
                    "reason_codes",
                    "policy_version",
                    "decided_at",
                ]
            },
            "lifecycle": {
                "deletion": ["delete canonical and derived state"],
                "export": ["inventory exportable canonical records"],
                "retention": ["deterministic expiry"],
            },
        },
    }
    (machine / "ai_app_construction.json").write_text(
        json.dumps(construction),
        encoding="utf-8",
    )
    topology = {
        "stores": [
            {
                "id": "governance-lifecycle-sqlite",
                "production_role": "authoritative lifecycle metadata",
                "evidence": [
                    "skeleton/vault/data_lifecycle.py",
                    "skeleton/vault/governance_registry.py",
                    "skeleton/vault/lifecycle_adapters.py",
                    "skeleton/api/server.py",
                ],
            }
        ]
    }
    (machine / "state_topology.json").write_text(
        json.dumps(topology),
        encoding="utf-8",
    )


def _valid_repo(tmp_path: Path) -> Path:
    root = tmp_path
    for rel, tokens in BOUNDARIES.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(f"# {token}" for token in tokens) + "\n",
            encoding="utf-8",
        )

    for source_rel, mirror_rel in MIRROR_PAIRS:
        source = root / source_rel
        mirror = root / mirror_rel
        mirror.parent.mkdir(parents=True, exist_ok=True)
        mirror.write_bytes(source.read_bytes())

    _write_machine_contract(root)
    return root


def test_independent_governance_verifier_accepts_canonical_boundaries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _valid_repo(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "governance-head")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "governance-head"
    assert len(receipt["boundary_digests"]) == len(BOUNDARIES)
    assert len(receipt["mirror_pairs"]) == len(MIRROR_PAIRS)
    assert receipt["blueprint_digest"]
    assert receipt["state_topology_digest"]


def test_independent_governance_verifier_rejects_fail_closed_contract_loss(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    contract_path = root / "machine" / "ai_app_construction.json"
    payload = json.loads(contract_path.read_text(encoding="utf-8"))
    payload["governance_runtime_blueprint"]["fail_closed"] = [
        "unknown tenant"
    ]
    contract_path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "governance blueprint lost fail-closed invariant: purpose mismatch"
        in error
        for error in receipt["errors"]
    )


def test_independent_governance_verifier_rejects_authority_topology_loss(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    topology_path = root / "machine" / "state_topology.json"
    topology_path.write_text(
        json.dumps({"stores": []}),
        encoding="utf-8",
    )

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "state topology lost governance authority token: governance-lifecycle-sqlite"
        in error
        for error in receipt["errors"]
    )


def test_independent_governance_verifier_rejects_boundary_token_loss(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    target = root / "skeleton" / "vault" / "governance_registry.py"
    target.write_text("# GovernanceRegistry\n", encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "skeleton/vault/governance_registry.py lost governance token: DataLifecycleRegistry"
        in error
        for error in receipt["errors"]
    )


def test_independent_governance_verifier_rejects_ai_mirror_drift(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    mirror = (
        root
        / "skeleton"
        / "ai"
        / "runtime"
        / "vault"
        / "governance_registry.py"
    )
    mirror.write_text("# drift\n", encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "canonical AI mirror drift: skeleton/vault/governance_registry.py"
        in error
        for error in receipt["errors"]
    )
