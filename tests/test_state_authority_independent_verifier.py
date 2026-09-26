from __future__ import annotations

import json
from pathlib import Path
import shutil

from scripts import verify_state_authority_closure as verifier


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _fixture_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    topology = json.loads(
        (verifier.ROOT / verifier.TOPOLOGY_PATH).read_text(
            encoding="utf-8"
        )
    )
    policy = json.loads(
        (verifier.ROOT / verifier.BACKUP_POLICY_PATH).read_text(
            encoding="utf-8"
        )
    )
    _write_json(root / verifier.TOPOLOGY_PATH, topology)
    _write_json(root / verifier.BACKUP_POLICY_PATH, policy)

    for relative in (
        verifier.COMPOSE_PATH,
        verifier.RECOVERY_WORKFLOW_PATH,
    ):
        source = verifier.ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    for relative in (
        Path("scripts/state_backup_bundle.py"),
        Path("scripts/state_recovery_drill.py"),
        Path("scripts/verify_state_authority_closure.py"),
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# fixture\n", encoding="utf-8")

    domains = {
        item["id"]: item
        for item in topology["state_domains"]
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    for domain_id in verifier.REQUIRED_AUTHORITIES:
        for relative in domains[domain_id].get("evidence", []):
            path = root / relative
            if path.exists():
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# evidence fixture\n", encoding="utf-8")

    return root


def _mutate_topology(root: Path, mutate) -> None:
    path = root / verifier.TOPOLOGY_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    _write_json(path, payload)


def _mutate_policy(root: Path, mutate) -> None:
    path = root / verifier.BACKUP_POLICY_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    _write_json(path, payload)


def test_repository_state_authority_verifier_accepts_current_contract() -> None:
    receipt = verifier.verify_repository(verifier.ROOT)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["verifier"] == "independent-state-authority-v1"
    assert len(receipt["authority_digest"]) == 64
    assert {
        item["id"]
        for item in receipt["authoritative_domains"]
    } == set(verifier.REQUIRED_AUTHORITIES)
    assert {
        item["id"]
        for item in receipt["derived_domains"]
    } == set(verifier.REQUIRED_DERIVED)


def test_verifier_rejects_authoritative_state_on_process_memory(
    tmp_path: Path,
) -> None:
    root = _fixture_root(tmp_path)

    def mutate(payload):
        domain = next(
            item
            for item in payload["state_domains"]
            if item["id"] == "canonical-operation-state"
        )
        domain["physical_store"] = "process-memory"

    _mutate_topology(root, mutate)
    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "canonical-operation-state must use operation-state-sqlite"
        in error
        for error in receipt["errors"]
    )
    assert any(
        "uses non-authoritative store class process-memory" in error
        for error in receipt["errors"]
    )


def test_verifier_rejects_projection_promoted_to_authority(
    tmp_path: Path,
) -> None:
    root = _fixture_root(tmp_path)

    def mutate(payload):
        domain = next(
            item
            for item in payload["state_domains"]
            if item["id"] == "backend-rag-local-chroma"
        )
        domain["source_of_truth"] = True
        domain["rebuildable"] = False

    _mutate_topology(root, mutate)
    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "backend-rag-local-chroma must not be source_of_truth" in error
        for error in receipt["errors"]
    )
    assert any(
        "backend-rag-local-chroma must be rebuildable" in error
        for error in receipt["errors"]
    )


def test_verifier_rejects_missing_required_backup_store(
    tmp_path: Path,
) -> None:
    root = _fixture_root(tmp_path)

    def mutate(payload):
        payload["stores"] = [
            item
            for item in payload["stores"]
            if item["file"] != "engine_pressure.sqlite"
        ]

    _mutate_policy(root, mutate)
    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "required backup files drifted" in error
        and "engine_pressure.sqlite" in error
        for error in receipt["errors"]
    )


def test_verifier_rejects_backup_restore_order_drift(
    tmp_path: Path,
) -> None:
    root = _fixture_root(tmp_path)

    def mutate(payload):
        payload["stores"][0], payload["stores"][1] = (
            payload["stores"][1],
            payload["stores"][0],
        )

    _mutate_policy(root, mutate)
    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert "backup stores must be declared in restore order" in receipt["errors"]


def test_verifier_rejects_lost_compose_persistence_binding(
    tmp_path: Path,
) -> None:
    root = _fixture_root(tmp_path)
    path = root / verifier.COMPOSE_PATH
    source = path.read_text(encoding="utf-8")
    source = source.replace(
        "SKL_ENGINE_QUOTA_STATE_PATH=/app/data/engine_quota.sqlite",
        "SKL_ENGINE_QUOTA_STATE_PATH=/tmp/engine_quota.sqlite",
    )
    path.write_text(source, encoding="utf-8")

    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "Compose lost durable binding: "
        "SKL_ENGINE_QUOTA_STATE_PATH=/app/data/engine_quota.sqlite"
        == error
        for error in receipt["errors"]
    )


def test_verifier_allows_other_explicit_unbound_gap_but_not_state_gap(
    tmp_path: Path,
) -> None:
    root = _fixture_root(tmp_path)
    initial = verifier.verify_repository(root)
    assert initial["valid"] is True

    def mutate(payload):
        domain = next(
            item
            for item in payload["state_domains"]
            if item["id"] == "verification-receipt-ledger"
        )
        domain["gap"] = "gap-state-authority-convergence"

    _mutate_topology(root, mutate)
    receipt = verifier.verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "state-authority gap still owns unbound domain "
        "verification-receipt-ledger"
        == error
        for error in receipt["errors"]
    )
