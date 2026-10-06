from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_vol002_architecture_fitness import (
    REQUIRED_VOL002_EVALUATIONS,
    REQUIRED_VOL002_PATHS,
    REQUIRED_VOL002_TESTS,
    verify_repository,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _valid_repo(tmp_path: Path) -> Path:
    root = tmp_path
    for relative in ("skeleton", "machine", "scripts", "docs"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    (root / "docs" / "ARCHITECTURE_MAP.md").write_text(
        "# architecture\n",
        encoding="utf-8",
    )
    (root / "scripts" / "check_architecture_map.py").write_text(
        "# canonical validator\n",
        encoding="utf-8",
    )

    architecture = {
        "sources": {
            "runtime_contract": "skeleton/app/manifest.json",
            "validator": "scripts/check_architecture_map.py",
            "human_map": "docs/ARCHITECTURE_MAP.md",
        },
        "canonical_roots": [
            {
                "id": "engine-runtime",
                "path": "skeleton",
                "class": "runtime",
                "owner": "engine",
                "change_lane": "engine",
            },
            {
                "id": "machine-control",
                "path": "machine",
                "class": "control",
                "owner": "repository-machine",
                "change_lane": "machine",
            },
            {
                "id": "operator-tooling",
                "path": "scripts",
                "class": "tooling",
                "owner": "operators",
                "change_lane": "tooling",
            },
            {
                "id": "documentation",
                "path": "docs",
                "class": "documentation",
                "owner": "architecture",
                "change_lane": "docs",
            },
        ],
        "zones": [
            {
                "id": "engine",
                "roots": ["skeleton"],
                "may_depend_on": [],
            },
            {
                "id": "machine",
                "roots": ["machine"],
                "may_depend_on": [],
            },
            {
                "id": "tooling",
                "roots": ["scripts"],
                "may_depend_on": ["engine", "machine"],
            },
            {
                "id": "knowledge",
                "roots": ["docs"],
                "may_depend_on": ["engine", "machine", "tooling"],
            },
        ],
        "runtime_nodes": [
            {
                "id": "engine",
                "zone": "engine",
                "manifest_service": "engine",
                "path": "skeleton",
                "kind": "python",
                "canonical": True,
                "depends_on": [],
            }
        ],
        "top_level_policy": {
            "runtime_roots": ["skeleton"],
        },
    }
    _write_json(root / "machine" / "architecture.json", architecture)

    manifest = {
        "services": [
            {
                "name": "engine",
                "path": "skeleton",
                "kind": "python",
                "canonical": True,
                "depends_on": [],
            }
        ]
    }
    _write_json(root / "skeleton" / "app" / "manifest.json", manifest)

    master = {
        "volumes": [
            {
                "key": "VOL-002",
                "title": "System Architecture",
                "scope": "canonical-plan",
                "implementation_status": "implemented",
                "requirements": [
                    "Maintain one canonical architecture graph for roots, ownership zones, runtime DAGs and interfaces.",
                    "Reject illegal dependencies and undeclared production components before dependency-heavy tests.",
                    "Represent target/current drift as explicit gaps rather than implicit exceptions.",
                ],
                "implementation_paths": sorted(REQUIRED_VOL002_PATHS),
                "tests": sorted(REQUIRED_VOL002_TESTS),
                "evaluations": sorted(REQUIRED_VOL002_EVALUATIONS),
                "gaps": [
                    "independent exact-head VOL-002 Architecture Fitness and Ownership Gate qualification remains pending"
                ],
                "completion_checkbox": False,
                "completion_checkbox_mark": "[ ]",
                "enterprise_grade_state": "designed",
                "enterprise_grade_target": "enterprise_qualified",
            }
        ]
    }
    _write_json(root / "machine" / "ai_master_plan.json", master)
    return root


def test_independent_architecture_verifier_accepts_closed_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _valid_repo(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "architecture-head")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "architecture-head"
    assert receipt["volume"] == "VOL-002"
    assert receipt["canonical_root_ids"] == [
        "documentation",
        "engine-runtime",
        "machine-control",
        "operator-tooling",
    ]
    assert receipt["runtime_node_ids"] == ["engine"]
    assert len(receipt["receipt_digest"]) == 64


def test_independent_architecture_verifier_rejects_duplicate_root_ownership(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine" / "architecture.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    duplicate = dict(payload["canonical_roots"][0])
    duplicate["id"] = "engine-shadow"
    payload["canonical_roots"].append(duplicate)
    _write_json(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("multiply owned" in error for error in receipt["errors"])


def test_independent_architecture_verifier_rejects_zone_cycle(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine" / "architecture.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    engine = next(row for row in payload["zones"] if row["id"] == "engine")
    engine["may_depend_on"] = ["tooling"]
    _write_json(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "zone dependency graph contains cycle" in error
        for error in receipt["errors"]
    )


def test_independent_architecture_verifier_rejects_runtime_manifest_drift(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "skeleton" / "app" / "manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["services"][0]["kind"] = "shadow-runtime"
    _write_json(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert "runtime service engine.kind drift" in receipt["errors"]


def test_independent_architecture_verifier_rejects_unknown_runtime_dependency(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine" / "architecture.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["runtime_nodes"][0]["depends_on"] = ["ghost"]
    _write_json(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("depends on unknown 'ghost'" in error for error in receipt["errors"])


def test_independent_architecture_verifier_rejects_missing_source_path(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine" / "architecture.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["sources"]["human_map"] = "docs/MISSING.md"
    _write_json(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("points to missing path" in error for error in receipt["errors"])


def test_independent_architecture_verifier_rejects_missing_masterplan_binding(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine" / "ai_master_plan.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["volumes"][0]["evaluations"].remove(
        "scripts/verify_vol002_architecture_fitness.py"
    )
    _write_json(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "VOL-002 evaluation binding incomplete" in error
        for error in receipt["errors"]
    )


def test_independent_architecture_verifier_rejects_requirement_erosion(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine" / "ai_master_plan.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["volumes"][0]["requirements"] = ["Architecture exists."]
    _write_json(path, payload)

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any("VOL-002 lost requirement invariant" in error for error in receipt["errors"])
