from __future__ import annotations

import json
from pathlib import Path

from scripts.verify_cognitive_execution_closure import (
    BOUNDARIES,
    EXPECTED_DEPENDENCIES,
    MIRROR_PAIRS,
    verify_repository,
)


def _write_machine_contracts(root: Path) -> None:
    machine = root / "machine"
    machine.mkdir(parents=True, exist_ok=True)

    handoff = {
        "entries": [
            {
                "gap": "gap-cognitive-execution-loop",
                "depends_on": sorted(EXPECTED_DEPENDENCIES),
                "implementation_status": "implementation-complete",
                "closure_gate": (
                    "one operation can deterministically retrieve, reason, call "
                    "governed tools, wait/resume, verify, persist and stream a "
                    "terminal answer without bypassing any canonical plane"
                ),
            }
        ]
    }
    (machine / "ai_implementation_handoff.json").write_text(
        json.dumps(handoff),
        encoding="utf-8",
    )

    gap_rows = [
        {"id": "gap-cognitive-execution-loop", "status": "open"}
    ]
    gap_rows.extend(
        {"id": gap_id, "status": "open"}
        for gap_id in sorted(EXPECTED_DEPENDENCIES)
    )
    construction = {
        "gap_register": gap_rows,
        "cognitive_runtime_blueprint": {
            "gap": "gap-cognitive-execution-loop",
            "status": "implemented-pending-closure",
            "target_modules": {
                "contracts": {
                    "path": "skeleton/contracts/ai_execution.py",
                },
                "runtime": {
                    "path": "skeleton/intelligence/execution_runtime.py",
                },
                "repository": {
                    "path": "skeleton/persistence/execution_repository.py",
                },
                "provider_boundary": {
                    "path": "skeleton/provider_runtime.py",
                },
            },
        },
    }
    (machine / "ai_app_construction.json").write_text(
        json.dumps(construction),
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

    _write_machine_contracts(root)
    return root


def test_independent_cognitive_verifier_accepts_canonical_boundaries(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = _valid_repo(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "cognitive-head")

    receipt = verify_repository(root)

    assert receipt["valid"] is True
    assert receipt["errors"] == []
    assert receipt["head_sha"] == "cognitive-head"
    assert len(receipt["boundary_digests"]) == len(BOUNDARIES)
    assert len(receipt["mirror_pairs"]) == len(MIRROR_PAIRS)
    assert set(receipt["dependency_graph"]) == EXPECTED_DEPENDENCIES


def test_independent_cognitive_verifier_rejects_runtime_provider_sdk_drift(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    runtime = root / "skeleton" / "intelligence" / "execution_runtime.py"
    runtime.write_text(
        runtime.read_text(encoding="utf-8") + "\nfrom openai import AsyncOpenAI\n",
        encoding="utf-8",
    )

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "regained direct provider ownership" in error
        for error in receipt["errors"]
    )


def test_independent_cognitive_verifier_rejects_finalization_contract_loss(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    repository = root / "skeleton" / "persistence" / "execution_repository.py"
    repository.write_text(
        "# class SQLiteExecutionRepository\n# def checkpoint(\n",
        encoding="utf-8",
    )

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "lost cognitive execution token: def stage_finalization("
        in error
        for error in receipt["errors"]
    )


def test_independent_cognitive_verifier_rejects_dependency_drift(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine" / "ai_implementation_handoff.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["entries"][0]["depends_on"] = ["gap-cost-admission"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "cognitive execution dependency graph mismatch" in error
        for error in receipt["errors"]
    )


def test_independent_cognitive_verifier_rejects_ai_mirror_drift(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    mirror = (
        root
        / "skeleton"
        / "ai"
        / "runtime"
        / "intelligence"
        / "execution_runtime.py"
    )
    mirror.write_text("# drift\n", encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "canonical AI mirror drift: skeleton/intelligence/execution_runtime.py"
        in error
        for error in receipt["errors"]
    )


def test_closed_cognitive_gap_rejects_open_dependencies(
    tmp_path: Path,
) -> None:
    root = _valid_repo(tmp_path)
    path = root / "machine" / "ai_app_construction.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["gap_register"][0]["status"] = "closed"
    path.write_text(json.dumps(payload), encoding="utf-8")

    receipt = verify_repository(root)

    assert receipt["valid"] is False
    assert any(
        "closed cognitive execution gap has non-closed dependencies"
        in error
        for error in receipt["errors"]
    )
