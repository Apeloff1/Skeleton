"""Regression tests for fail-closed temporary security exception governance."""
from __future__ import annotations

from datetime import date
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_security_exceptions.py"
SPEC = importlib.util.spec_from_file_location("check_security_exceptions_gate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


TODAY = date(2026, 9, 28)


def _entry(**overrides):
    payload = {
        "id": "SEC-123",
        "control": "workflow-output-redaction",
        "paths": ["backend/scripts/check_workflow_security.py"],
        "reason": "A narrow migration needs one temporary compatibility window.",
        "compensating_control": "Merge Readiness still runs secret and malware scans.",
        "owner": "@owner",
        "tracking_issue": 540,
        "approved_by": "@reviewer",
        "approved_on": "2026-09-20",
        "expires_on": "2026-10-10",
    }
    payload.update(overrides)
    return payload


def _registry(*entries):
    return {"schema_version": 1, "entries": list(entries)}


def _write(path: Path, payload) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_empty_registry_is_clean(tmp_path: Path) -> None:
    path = _write(tmp_path / "registry.json", _registry())
    assert checker.validate_file(path, today=TODAY) == ()


def test_valid_exception_is_bounded_and_reported(tmp_path: Path) -> None:
    path = _write(tmp_path / "registry.json", _registry(_entry()))
    assert checker.validate_file(path, today=TODAY) == ("SEC-123",)


def test_expired_exception_fails_closed(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "registry.json",
        _registry(_entry(expires_on="2026-09-28")),
    )
    with pytest.raises(checker.SecurityExceptionPolicyError, match="expired"):
        checker.validate_file(path, today=TODAY)


def test_exception_over_thirty_days_is_rejected(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "registry.json",
        _registry(
            _entry(
                approved_on="2026-09-01",
                expires_on="2026-10-02",
            )
        ),
    )
    with pytest.raises(checker.SecurityExceptionPolicyError, match="maximum is 30"):
        checker.validate_file(path, today=TODAY)


@pytest.mark.parametrize(
    "scope",
    [
        ".",
        "..",
        "/backend/auth.py",
        "backend",
        "backend/**",
        "backend/[ab].py",
        r"backend\auth.py",
    ],
)
def test_broad_or_ambiguous_scope_is_rejected(tmp_path: Path, scope: str) -> None:
    path = _write(
        tmp_path / "registry.json",
        _registry(_entry(paths=[scope])),
    )
    with pytest.raises(checker.SecurityExceptionPolicyError):
        checker.validate_file(path, today=TODAY)


def test_exact_component_scope_is_allowed(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "registry.json",
        _registry(_entry(paths=["backend/auth"])),
    )
    assert checker.validate_file(path, today=TODAY) == ("SEC-123",)


def test_unknown_or_missing_fields_fail_closed(tmp_path: Path) -> None:
    extra = _entry()
    extra["ticket"] = "SEC-1"
    path = _write(tmp_path / "extra.json", _registry(extra))
    with pytest.raises(checker.SecurityExceptionPolicyError, match="keys mismatch"):
        checker.validate_file(path, today=TODAY)

    missing = _entry()
    missing.pop("approved_by")
    path = _write(tmp_path / "missing.json", _registry(missing))
    with pytest.raises(checker.SecurityExceptionPolicyError, match="keys mismatch"):
        checker.validate_file(path, today=TODAY)


def test_duplicate_ids_fail_closed(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "registry.json",
        _registry(_entry(), _entry(reason="Different reason.")),
    )
    with pytest.raises(checker.SecurityExceptionPolicyError, match="duplicate exception id"):
        checker.validate_file(path, today=TODAY)


def test_duplicate_json_keys_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.write_text(
        '{"schema_version":1,"schema_version":1,"entries":[]}',
        encoding="utf-8",
    )
    with pytest.raises(checker.SecurityExceptionPolicyError, match="duplicate JSON key"):
        checker.validate_file(path, today=TODAY)


@pytest.mark.parametrize("field", ["owner", "approved_by"])
def test_review_identity_is_required(tmp_path: Path, field: str) -> None:
    path = _write(
        tmp_path / "registry.json",
        _registry(_entry(**{field: "not a valid login!"})),
    )
    with pytest.raises(checker.SecurityExceptionPolicyError, match="GitHub-style login"):
        checker.validate_file(path, today=TODAY)


def test_tracking_issue_must_be_positive_integer(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "registry.json",
        _registry(_entry(tracking_issue=0)),
    )
    with pytest.raises(checker.SecurityExceptionPolicyError, match="positive issue number"):
        checker.validate_file(path, today=TODAY)


def test_future_approval_is_rejected(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "registry.json",
        _registry(
            _entry(
                approved_on="2026-09-29",
                expires_on="2026-10-10",
            )
        ),
    )
    with pytest.raises(checker.SecurityExceptionPolicyError, match="future"):
        checker.validate_file(path, today=TODAY)


def test_registry_size_is_bounded(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    path.write_text(" " * (checker.MAX_REGISTRY_BYTES + 1), encoding="utf-8")
    with pytest.raises(checker.SecurityExceptionPolicyError, match="byte limit"):
        checker.validate_file(path, today=TODAY)


def test_repository_registry_is_clean() -> None:
    assert checker.validate_file(checker.DEFAULT_REGISTRY, today=TODAY) == ()


def test_canonical_quality_gate_wires_exception_policy() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / "scripts" / "quality-gates.sh").read_text(encoding="utf-8")
    assert "python backend/scripts/check_security_exceptions.py" in source
    assert "backend/tests/test_security_exception_policy.py" in source
