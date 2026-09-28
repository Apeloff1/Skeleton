from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from scripts.check_p1_terminal_evidence_policy import (
    BACKLOG_PATH,
    MAP_PATH,
    POLICY_PATH,
    ROOT,
    TerminalPolicyError,
    validate_repository,
)


def _repo(tmp_path: Path) -> Path:
    for relative in (POLICY_PATH, BACKLOG_PATH, MAP_PATH):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    policy = json.loads(
        (tmp_path / POLICY_PATH).read_text(encoding="utf-8")
    )
    for row in policy["required_receipts"]:
        for raw in row["test_paths"]:
            target = tmp_path / raw
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# fixture\n", encoding="utf-8")
    return tmp_path


def _mutate(root: Path, relative: Path, mutate) -> None:
    path = root / relative
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_current_terminal_evidence_policy_is_valid() -> None:
    summary = validate_repository(ROOT)
    assert summary["valid"] is True
    assert summary["required_receipt_count"] == 10
    assert summary["primary_volume_count"] > 0
    assert summary["promotion_authority"] is False
    assert summary["signed_promotion"] is False


def test_dependency_drift_is_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    def reverse_prom_dependencies(value):
        prom = next(
            row for row in value["tasks"]
            if row["task_id"] == "P1-PROM-01"
        )
        prom["depends_on"].reverse()

    _mutate(
        root,
        BACKLOG_PATH,
        reverse_prom_dependencies,
    )
    with pytest.raises(
        TerminalPolicyError,
        match="dependency order/identity drift",
    ):
        validate_repository(root)


def test_receipt_accountability_drift_is_rejected(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _mutate(
        root,
        POLICY_PATH,
        lambda value: value["required_receipts"][0].update(
            {"accountability_id": "ACC-P1-WRONG"}
        ),
    )
    with pytest.raises(
        TerminalPolicyError,
        match="receipt identity drift",
    ):
        validate_repository(root)


def test_promotion_authority_cannot_be_enabled(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _mutate(
        root,
        POLICY_PATH,
        lambda value: value.update(
            {"promotion_authority": True}
        ),
    )
    with pytest.raises(
        TerminalPolicyError,
        match="promotion_authority must remain false",
    ):
        validate_repository(root)


def test_missing_terminal_test_path_is_rejected(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _mutate(
        root,
        POLICY_PATH,
        lambda value: value["required_receipts"][0][
            "test_paths"
        ].append("tests/does_not_exist.py"),
    )
    with pytest.raises(
        TerminalPolicyError,
        match="missing test path",
    ):
        validate_repository(root)


def test_primary_volume_duplicate_is_rejected(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)

    def duplicate(value):
        lanes = value["lanes"]
        source = next(
            lane for lane in lanes
            if lane["primary_volume_refs"]
        )
        target = next(
            lane for lane in lanes
            if lane is not source
        )
        target["primary_volume_refs"].append(
            source["primary_volume_refs"][0]
        )

    _mutate(root, MAP_PATH, duplicate)
    with pytest.raises(
        TerminalPolicyError,
        match="ownership is duplicated",
    ):
        validate_repository(root)
