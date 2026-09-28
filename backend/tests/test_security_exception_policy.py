"""Regression tests for time-bounded security-exception policy."""
from __future__ import annotations

from datetime import date
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_security_exceptions.py"
SPEC = importlib.util.spec_from_file_location("check_security_exceptions", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


def _valid_exception(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "SEC-2026-001",
        "control": "repository-python-sast",
        "scope": ["skeleton/example.py"],
        "reason": "Upstream parser migration requires a short compatibility window.",
        "compensating_control": "Focused regression rejects untrusted input before this boundary.",
        "owner": "maintainer@example",
        "tracking_issue": 540,
        "review_pr": 2000,
        "approved_by": ["reviewer@example"],
        "starts_on": "2026-09-01",
        "expires_on": "2026-09-30",
    }
    payload.update(overrides)
    return payload


def _registry(*entries: dict[str, object]) -> dict[str, object]:
    return {"schema": 1, "exceptions": list(entries)}


def test_repository_registry_is_valid_and_current() -> None:
    entries = checker.validate_file(
        checker.DEFAULT_REGISTRY,
        today=date(2026, 9, 28),
    )
    assert entries == ()


def test_valid_exception_is_explicit_reviewed_and_time_bounded() -> None:
    entries = checker.validate_registry(
        _registry(_valid_exception()),
        today=date(2026, 9, 28),
    )

    assert len(entries) == 1
    assert entries[0]["id"] == "SEC-2026-001"
    assert entries[0]["tracking_issue"] == 540
    assert entries[0]["review_pr"] == 2000
    assert entries[0]["approved_by"] == ("reviewer@example",)
    assert entries[0]["scope"] == ("skeleton/example.py",)


def test_expired_exception_fails_closed() -> None:
    with pytest.raises(checker.SecurityExceptionPolicyError, match="expired"):
        checker.validate_registry(
            _registry(
                _valid_exception(
                    starts_on="2026-08-01",
                    expires_on="2026-08-20",
                )
            ),
            today=date(2026, 9, 28),
        )


def test_future_exception_cannot_prearm_a_bypass() -> None:
    with pytest.raises(checker.SecurityExceptionPolicyError, match="starts in the future"):
        checker.validate_registry(
            _registry(
                _valid_exception(
                    starts_on="2026-10-01",
                    expires_on="2026-10-20",
                )
            ),
            today=date(2026, 9, 28),
        )


def test_exception_lifetime_cannot_exceed_thirty_days() -> None:
    with pytest.raises(checker.SecurityExceptionPolicyError, match="30-day"):
        checker.validate_registry(
            _registry(
                _valid_exception(
                    starts_on="2026-09-01",
                    expires_on="2026-10-02",
                )
            ),
            today=date(2026, 9, 28),
        )


@pytest.mark.parametrize(
    "scope",
    [
        ["*"],
        ["**"],
        ["backend/**"],
        ["/backend/routes.py"],
        ["backend/../secrets.txt"],
        ["backend/routes.py\nother"],
    ],
)
def test_scope_must_be_exact_and_narrow(scope: list[str]) -> None:
    with pytest.raises(checker.SecurityExceptionPolicyError):
        checker.validate_registry(
            _registry(_valid_exception(scope=scope)),
            today=date(2026, 9, 28),
        )


def test_review_evidence_is_mandatory() -> None:
    with pytest.raises(checker.SecurityExceptionPolicyError, match="approved_by"):
        checker.validate_registry(
            _registry(_valid_exception(approved_by=[])),
            today=date(2026, 9, 28),
        )

    with pytest.raises(checker.SecurityExceptionPolicyError, match="review_pr"):
        checker.validate_registry(
            _registry(_valid_exception(review_pr=0)),
            today=date(2026, 9, 28),
        )


def test_duplicate_exception_ids_fail_closed() -> None:
    with pytest.raises(checker.SecurityExceptionPolicyError, match="duplicate exception id"):
        checker.validate_registry(
            _registry(_valid_exception(), _valid_exception()),
            today=date(2026, 9, 28),
        )


def test_unknown_or_missing_fields_fail_closed() -> None:
    extra = _valid_exception()
    extra["allow_everything"] = True
    with pytest.raises(checker.SecurityExceptionPolicyError, match="keys mismatch"):
        checker.validate_registry(
            _registry(extra),
            today=date(2026, 9, 28),
        )

    missing = _valid_exception()
    del missing["compensating_control"]
    with pytest.raises(checker.SecurityExceptionPolicyError, match="keys mismatch"):
        checker.validate_registry(
            _registry(missing),
            today=date(2026, 9, 28),
        )


def test_duplicate_json_keys_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "exceptions.json"
    path.write_text(
        '{"schema":1,"schema":1,"exceptions":[]}',
        encoding="utf-8",
    )

    with pytest.raises(checker.SecurityExceptionPolicyError, match="duplicate JSON key"):
        checker.load_registry(path)


def test_cli_returns_nonzero_for_expired_registry(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "exceptions.json"
    path.write_text(
        json.dumps(
            _registry(
                _valid_exception(
                    starts_on="2026-08-01",
                    expires_on="2026-08-20",
                )
            )
        ),
        encoding="utf-8",
    )

    result = checker.main([str(path), "--today", "2026-09-28"])

    assert result == 1
    assert "expired" in capsys.readouterr().out
