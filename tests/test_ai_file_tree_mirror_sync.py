"""Non-destructive, deterministic AI mirror synchronization contracts."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.sync_ai_file_tree_mirrors import (
    _safe_path,
    apply_mirrors,
    main,
    plan_mirrors,
)


SOURCE = "skeleton/contracts/runtime_contract.py"
DEST = "skeleton/ai/runtime/contracts/runtime_contract.py"


def _fixture(root: Path, *, mapping: dict | None = None) -> tuple[dict, set[str]]:
    source = root / SOURCE
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("RESULT = 7\n", encoding="utf-8")
    definition = {
        "id": "AIFT-TEST",
        "kind": "tree",
        "source": "skeleton/contracts",
        "destination": "skeleton/ai/runtime/contracts",
    }
    definition.update(mapping or {})
    return {"mappings": [definition]}, {SOURCE}


def test_plan_is_deterministic_and_apply_creates_only_missing_mirror(tmp_path: Path):
    manifest, tracked = _fixture(tmp_path)
    first = plan_mirrors(tmp_path, manifest, tracked)
    second = plan_mirrors(tmp_path, manifest, tracked)
    assert first == second
    additions, conflicts = first
    assert conflicts == []
    assert [record["destination"] for record in additions] == [DEST]
    assert additions[0]["source_sha256"] == hashlib.sha256(
        (tmp_path / SOURCE).read_bytes()
    ).hexdigest()
    assert apply_mirrors(tmp_path, additions) == 1
    assert (tmp_path / DEST).read_bytes() == (tmp_path / SOURCE).read_bytes()
    assert plan_mirrors(tmp_path, manifest, tracked) == ([], [])


def test_existing_drift_is_reported_and_never_overwritten(tmp_path: Path):
    manifest, tracked = _fixture(tmp_path)
    destination = tmp_path / DEST
    destination.parent.mkdir(parents=True)
    destination.write_text("RESULT = 900\n", encoding="utf-8")
    additions, conflicts = plan_mirrors(tmp_path, manifest, tracked)
    assert additions == []
    assert conflicts[0]["reason"].startswith("existing destination differs")
    assert destination.read_text() == "RESULT = 900\n"


def test_python_ast_parity_accepts_formatting_without_overwriting(tmp_path: Path):
    manifest, tracked = _fixture(tmp_path)
    destination = tmp_path / DEST
    destination.parent.mkdir(parents=True)
    destination.write_text("RESULT=7\n\n", encoding="utf-8")
    assert plan_mirrors(tmp_path, manifest, tracked) == ([], [])


@pytest.mark.parametrize(
    "mapping",
    [
        {"overlay_children": ["runtime_contract.py"]},
        {"source_exclusions": ["runtime_contract.py"]},
    ],
)
def test_explicit_overlays_and_source_exclusions_are_not_copied(tmp_path: Path, mapping: dict):
    manifest, tracked = _fixture(tmp_path, mapping=mapping)
    assert plan_mirrors(tmp_path, manifest, tracked) == ([], [])


def test_intentional_non_owning_facade_preserves_distinct_implementation(tmp_path: Path):
    manifest, tracked = _fixture(
        tmp_path,
        mapping={
            "parity_exceptions": [
                {
                    "path": "runtime_contract.py",
                    "mode": "compatibility_facade",
                    "facade_required_import": "from skeleton.contracts import",
                }
            ]
        },
    )
    destination = tmp_path / DEST
    destination.parent.mkdir(parents=True)
    destination.write_text("from skeleton.contracts import runtime_contract\n", encoding="utf-8")
    assert plan_mirrors(tmp_path, manifest, tracked) == ([], [])
    assert destination.read_text().startswith("from skeleton.contracts")


def test_overlapping_mapping_requires_identical_source_digest(tmp_path: Path):
    manifest, tracked = _fixture(tmp_path)
    other = tmp_path / "skeleton" / "another" / "runtime_contract.py"
    other.parent.mkdir(parents=True)
    other.write_text("RESULT = 8\n", encoding="utf-8")
    tracked.add("skeleton/another/runtime_contract.py")
    manifest["mappings"].append(
        {
            "id": "AIFT-SECOND",
            "kind": "tree",
            "source": "skeleton/another",
            "destination": "skeleton/ai/runtime/contracts",
        }
    )
    with pytest.raises(ValueError, match="overlapping mappings"):
        plan_mirrors(tmp_path, manifest, tracked)


def test_source_mutation_after_plan_is_never_applied(tmp_path: Path):
    manifest, tracked = _fixture(tmp_path)
    additions, _ = plan_mirrors(tmp_path, manifest, tracked)
    (tmp_path / SOURCE).write_text("RESULT = 8\n", encoding="utf-8")
    with pytest.raises(ValueError, match="source changed"):
        apply_mirrors(tmp_path, additions)
    assert not (tmp_path / DEST).exists()


def test_destination_is_not_clobbered_after_plan(tmp_path: Path):
    manifest, tracked = _fixture(tmp_path)
    additions, _ = plan_mirrors(tmp_path, manifest, tracked)
    target = tmp_path / DEST
    target.parent.mkdir(parents=True)
    target.write_text("RESULT = 123\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        apply_mirrors(tmp_path, additions)
    assert target.read_text() == "RESULT = 123\n"


def test_unsafe_paths_are_rejected(tmp_path: Path):
    for path in ("../secret", "/tmp/secret", "skeleton\\secret"):
        with pytest.raises(ValueError):
            _safe_path(tmp_path, path)


def test_cli_check_apply_and_receipt_are_stable(tmp_path: Path, capsys):
    manifest, _ = _fixture(tmp_path)
    manifest_file = tmp_path / "machine" / "ai_file_tree.json"
    manifest_file.parent.mkdir(parents=True)
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", SOURCE], cwd=tmp_path, check=True)
    common = ["--root", str(tmp_path), "--manifest", "machine/ai_file_tree.json"]
    assert main(common) == 1
    check = json.loads(capsys.readouterr().out)
    assert check["planned"] == 1 and check["applied"] == 0
    assert len(check["receipt_sha256"]) == 64
    assert main(common + ["--apply"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["applied"] == 1
    assert main(common) == 0
    assert json.loads(capsys.readouterr().out)["planned"] == 0
