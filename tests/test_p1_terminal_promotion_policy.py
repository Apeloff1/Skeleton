from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from scripts.check_p1_terminal_promotion_policy import (
    BACKLOG_PATH,
    POLICY_PATH,
    PROM01_POLICY_PATH,
    PROM02_POLICY_PATH,
    ROOT,
    TerminalPromotionPolicyError,
    validate_repository,
)


def _repo(tmp_path: Path) -> Path:
    for relative in (
        POLICY_PATH,
        BACKLOG_PATH,
        PROM01_POLICY_PATH,
        PROM02_POLICY_PATH,
    ):
        source = ROOT / relative
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return tmp_path


def _mutate(root: Path, relative: Path, mutate) -> None:
    path = root / relative
    value = json.loads(path.read_text(encoding="utf-8"))
    mutate(value)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_current_terminal_promotion_policy_is_valid() -> None:
    summary = validate_repository(ROOT)
    assert summary["valid"] is True
    assert summary["external_signature_required_for_promotion"] is True
    assert summary["allow_explicit_rejection_without_signature"] is True
    assert summary["ci_may_generate_promotion_signature"] is False


def test_ci_cannot_be_allowed_to_generate_signature(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _mutate(
        root,
        POLICY_PATH,
        lambda value: value.update(
            {"ci_may_generate_promotion_signature": True}
        ),
    )
    with pytest.raises(
        TerminalPromotionPolicyError,
        match="must not generate",
    ):
        validate_repository(root)


def test_agent_signer_cannot_be_enabled(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _mutate(
        root,
        POLICY_PATH,
        lambda value: value["allowed_signer_types"].append("agent"),
    )
    with pytest.raises(
        TerminalPromotionPolicyError,
        match="allowed signer types drift",
    ):
        validate_repository(root)


def test_prom03_dependency_must_remain_prom02_only(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    def mutate(value):
        task = next(
            row for row in value["tasks"]
            if row["task_id"] == "P1-PROM-03"
        )
        task["depends_on"] = ["P1-PROM-01"]

    _mutate(root, BACKLOG_PATH, mutate)
    with pytest.raises(
        TerminalPromotionPolicyError,
        match="dependency identity drift",
    ):
        validate_repository(root)


def test_prom02_must_remain_non_authoritative(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _mutate(
        root,
        PROM02_POLICY_PATH,
        lambda value: value.update({"promotion_authority": True}),
    )
    with pytest.raises(
        TerminalPromotionPolicyError,
        match="PROM-02 must remain non-authoritative",
    ):
        validate_repository(root)


def test_external_signature_requirement_cannot_be_disabled(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    _mutate(
        root,
        POLICY_PATH,
        lambda value: value.update(
            {"external_signature_required_for_promotion": False}
        ),
    )
    with pytest.raises(
        TerminalPromotionPolicyError,
        match="must remain true",
    ):
        validate_repository(root)
