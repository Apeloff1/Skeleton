from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts.check_ai_training_resume import (
    CONTRACT,
    OWNERS,
    ROOT,
    TESTS,
    TrainingResumeContractError,
    validate,
)


def _fixture(tmp_path: Path) -> Path:
    for path in (str(CONTRACT), *OWNERS.values(), *TESTS):
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, destination)
    return tmp_path


def _mutate(root: Path, field: str, value: object) -> None:
    path = root / CONTRACT
    contract = json.loads(path.read_text(encoding="utf-8"))
    cursor = contract
    parts = field.split(".")
    for part in parts[:-1]:
        cursor = cursor[part]
    cursor[parts[-1]] = value
    path.write_text(json.dumps(contract), encoding="utf-8")


def _git_head(root: Path) -> str:
    subprocess.run(["git", "init", "--quiet", str(root)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Contract test",
            "-c",
            "user.email=contract@example.invalid",
            "commit",
            "--quiet",
            "--allow-empty",
            "-m",
            "Contract fixture",
        ],
        check=True,
    )
    return subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()


def test_bounded_unpromoted_resume_contract() -> None:
    result = validate()
    assert result["implementation_status"] == "implemented_unpromoted"
    assert result["production_model_promotion_authorized"] is False
    assert result["distributed_neural_training_supported"] is False
    assert result["executable_test_count"] == 3


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "closed"),
        ("claim_scope", "all_native_training"),
        ("production_model_promotion_authorized", True),
        ("production_model_promotion_authorized", 0),
        ("distributed_neural_training_supported", True),
        ("completion_checkbox", True),
        ("verification_signed", True),
        ("canonical_owners.control", "skeleton/training/control.py"),
        ("persistence.authority", "process-local dictionary"),
        ("persistence.commit_boundary", "commit payload separately after metadata"),
        ("binding.immutable_fields", ["manifest_digest"]),
        ("resume_payload.cursor_fields", ["document_index"]),
        ("limits.max_checkpoint_payload_bytes", 2**40),
        ("limits.default_checkpoint_every_documents", True),
        ("failures", ["log errors and continue"]),
        (
            "recovery",
            [
                "retrain every batch",
                "accept any model",
                "keep old leases",
                "overwrite previous cursor",
                "recompute terminal model",
                "trust cached state",
            ],
        ),
        ("tests", [TESTS[0]]),
        ("scope_limitations", ["reference estimator only"]),
    ],
)
def test_resume_contract_rejects_scope_or_authority_drift(
    tmp_path: Path, field: str, value: object
) -> None:
    root = _fixture(tmp_path)
    _mutate(root, field, value)
    with pytest.raises(TrainingResumeContractError):
        validate(root)


def test_missing_runtime_owner_fails_closed(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    (root / OWNERS["control"]).unlink()
    with pytest.raises(
        TrainingResumeContractError, match="cannot read executable surface"
    ):
        validate(root)


def test_missing_executable_regression_fails_closed(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    (root / TESTS[0]).write_text("# Regression deleted\n", encoding="utf-8")
    with pytest.raises(
        TrainingResumeContractError, match="executable resume regression missing"
    ):
        validate(root)


def test_missing_payload_identity_api_fails_closed(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    control = root / OWNERS["control"]
    import ast

    tree = ast.parse(control.read_text(encoding="utf-8"))
    checkpoint = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "TrainingCheckpoint"
    )
    annotation = next(
        node
        for node in checkpoint.body
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "payload_digest"
    )
    lines = control.read_text(encoding="utf-8").splitlines(keepends=True)
    del lines[annotation.lineno - 1 : annotation.end_lineno]
    control.write_text("".join(lines), encoding="utf-8")
    with pytest.raises(
        TrainingResumeContractError, match="lacks payload_digest identity"
    ):
        validate(root)


def test_exact_checked_out_head_is_reported(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    head = _git_head(root)
    assert validate(root, head=head)["reported_head"] == head


def test_mismatched_head_is_rejected_before_contract_validation(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    _git_head(root)
    with pytest.raises(TrainingResumeContractError, match="exact head mismatch"):
        validate(root, head="a" * 40)


def test_invalid_head_is_rejected_without_git_history(tmp_path: Path) -> None:
    with pytest.raises(TrainingResumeContractError, match="invalid exact head"):
        validate(tmp_path, head="not-a-commit")


def test_exact_head_requires_repository_identity(tmp_path: Path) -> None:
    with pytest.raises(TrainingResumeContractError, match="git identity unavailable"):
        validate(tmp_path, head="a" * 40)


def test_malformed_contract_fails_closed(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    (root / CONTRACT).write_text("{", encoding="utf-8")
    with pytest.raises(TrainingResumeContractError, match="cannot read"):
        validate(root)
