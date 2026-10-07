from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from scripts.check_p1_terminal_failure_journeys import (
    BACKLOG_PATH,
    MAP_PATH,
    POLICY_PATH,
    PROM01_POLICY_PATH,
    ROOT,
    TerminalJourneyPolicyError,
    validate_repository,
)


def _repo(tmp_path: Path) -> Path:
    for relative in (
        POLICY_PATH,
        MAP_PATH,
        BACKLOG_PATH,
        PROM01_POLICY_PATH,
    ):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    policy = json.loads(
        (tmp_path / POLICY_PATH).read_text(encoding="utf-8")
    )
    for row in policy["failure_families"]:
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


def test_current_terminal_failure_policy_is_valid() -> None:
    summary = validate_repository(ROOT)
    assert summary["valid"] is True
    assert summary["failure_family_count"] == 16
    assert summary["journey_class_count"] == 8
    assert summary["promotion_authority"] is False
    assert summary["signed_promotion"] is False


def test_failure_family_order_drift_is_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _mutate(
        root,
        POLICY_PATH,
        lambda value: value["failure_families"].reverse(),
    )
    with pytest.raises(
        TerminalJourneyPolicyError,
        match="failure family order/identity drift",
    ):
        validate_repository(root)


def test_execution_map_family_drift_is_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _mutate(
        root,
        MAP_PATH,
        lambda value: value["acceptance_program"][
            "required_failure_families"
        ].append("unmapped-new-family"),
    )
    with pytest.raises(
        TerminalJourneyPolicyError,
        match="failure family order/identity drift",
    ):
        validate_repository(root)


def test_missing_test_path_is_rejected(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _mutate(
        root,
        POLICY_PATH,
        lambda value: value["failure_families"][0]["test_paths"].append(
            "tests/does_not_exist.py"
        ),
    )
    with pytest.raises(
        TerminalJourneyPolicyError,
        match="missing test path",
    ):
        validate_repository(root)


def test_promotion_authority_cannot_be_enabled(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _mutate(
        root,
        POLICY_PATH,
        lambda value: value.update({"promotion_authority": True}),
    )
    with pytest.raises(
        TerminalJourneyPolicyError,
        match="promotion_authority must remain false",
    ):
        validate_repository(root)


def test_prom02_dependency_must_remain_prom01_only(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def mutate(value):
        task = next(
            row for row in value["tasks"]
            if row["task_id"] == "P1-PROM-02"
        )
        task["depends_on"] = ["P1-PROM-01", "P1-PROM-03"]

    _mutate(root, BACKLOG_PATH, mutate)
    with pytest.raises(
        TerminalJourneyPolicyError,
        match="PROM-02 dependency identity drift",
    ):
        validate_repository(root)


def test_journey_class_must_only_reference_canonical_family(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _mutate(
        root,
        POLICY_PATH,
        lambda value: value["journey_classes"]["partition"].append(
            "unknown-family"
        ),
    )
    with pytest.raises(
        TerminalJourneyPolicyError,
        match="unknown families",
    ):
        validate_repository(root)
