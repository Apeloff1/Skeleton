from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from skeleton.security.scanner_integrity import (
    RuleResult,
    ScanState,
    ScannerHarness,
    ScannerIntegrityError,
    Severity,
)
from skeleton.security.vuln_scanner import VulnScanner, VulnScannerError


def test_harness_requires_at_least_one_rule() -> None:
    scanner = ScannerHarness("security-test")
    with pytest.raises(ScannerIntegrityError, match="at least one rule"):
        scanner.scan()


def test_harness_does_not_report_score_before_scan() -> None:
    scanner = ScannerHarness("security-test")
    scanner.add_rule("clean", Severity.LOW, lambda _root: None, "none required")
    with pytest.raises(ScannerIntegrityError, match="has not run"):
        scanner.score()


def test_clean_scan_is_complete_and_merge_safe() -> None:
    scanner = ScannerHarness("security-test")
    scanner.add_rule("clean", Severity.LOW, lambda _root: None, "none required")

    report = scanner.scan()

    assert report.state is ScanState.COMPLETE
    assert report.complete is True
    assert report.findings == ()
    assert report.score() == 100.0
    assert len(report.evidence_digest) == 64
    report.assert_merge_safe()


def test_scanner_exception_becomes_critical_self_failure_without_raw_message() -> None:
    sensitive_marker = "SENSITIVE_FIXTURE_VALUE"

    def explode(_root: Path) -> None:
        raise RuntimeError(f"network failed with {sensitive_marker}")

    scanner = ScannerHarness("security-test")
    scanner.add_rule("exploding-rule", Severity.LOW, explode, "repair scanner")

    report = scanner.scan()

    assert report.complete
    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.scanner_failure is True
    assert finding.severity is Severity.CRITICAL
    assert finding.message == "scanner rule failed with RuntimeError"
    assert sensitive_marker not in finding.message
    assert report.score() == 60.0
    with pytest.raises(ScannerIntegrityError, match="self-failure"):
        report.assert_merge_safe()


def test_unsupported_probe_result_fails_closed() -> None:
    scanner = ScannerHarness("security-test")
    scanner.add_rule(
        "bad-result",
        Severity.LOW,
        lambda _root: {"unexpected": True},  # type: ignore[return-value]
        "repair scanner",
    )

    report = scanner.scan()

    assert len(report.scanner_failures) == 1
    assert report.scanner_failures[0].severity is Severity.CRITICAL
    with pytest.raises(ScannerIntegrityError):
        report.assert_merge_safe()


def test_high_finding_blocks_merge() -> None:
    scanner = ScannerHarness("security-test")
    scanner.add_rule(
        "high-risk",
        Severity.HIGH,
        lambda _root: "high-confidence security finding",
        "remove the unsafe configuration",
    )

    report = scanner.scan()

    assert report.score() == 75.0
    assert len(report.blocking_findings) == 1
    with pytest.raises(ScannerIntegrityError, match="blocking"):
        report.assert_merge_safe()


def test_structured_result_can_raise_severity_but_not_hide_finding() -> None:
    scanner = ScannerHarness("security-test")
    scanner.add_rule(
        "structured",
        Severity.LOW,
        lambda _root: RuleResult(
            message="runtime evidence requires containment",
            severity=Severity.CRITICAL,
            remediation="quarantine the affected principal",
            metadata=(("source", "runtime"),),
        ),
        "default remediation",
    )

    report = scanner.scan()

    finding = report.findings[0]
    assert finding.severity is Severity.CRITICAL
    assert finding.remediation == "quarantine the affected principal"
    assert dict(finding.metadata) == {"source": "runtime"}


@pytest.mark.parametrize(
    "severity",
    ["CRITICAL", "unknown", "", "severe", "p0"],
)
def test_invalid_severity_is_rejected(severity: str) -> None:
    scanner = ScannerHarness("security-test")
    with pytest.raises((ScannerIntegrityError, ValueError)):
        scanner.add_rule("test-rule", severity, lambda _root: None, "repair")


def test_duplicate_rule_names_are_rejected() -> None:
    scanner = ScannerHarness("security-test")
    scanner.add_rule("duplicate", Severity.LOW, lambda _root: None, "repair")
    with pytest.raises(ScannerIntegrityError, match="duplicate"):
        scanner.add_rule("duplicate", Severity.HIGH, lambda _root: None, "repair")


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "UPPERCASE",
        "white space",
        "",
        "x" * 129,
    ],
)
def test_rule_names_are_strict(name: str) -> None:
    scanner = ScannerHarness("security-test")
    with pytest.raises((ScannerIntegrityError, ValueError)):
        scanner.add_rule(name, Severity.LOW, lambda _root: None, "repair")


def test_control_characters_in_findings_fail_closed() -> None:
    scanner = ScannerHarness("security-test")
    scanner.add_rule(
        "control-output",
        Severity.LOW,
        lambda _root: "unsafe\x00diagnostic",
        "repair scanner",
    )

    report = scanner.scan()

    assert len(report.scanner_failures) == 1
    assert report.scanner_failures[0].severity is Severity.CRITICAL


def test_oversized_findings_fail_closed() -> None:
    scanner = ScannerHarness("security-test")
    scanner.add_rule(
        "oversized-output",
        Severity.LOW,
        lambda _root: "x" * 513,
        "repair scanner",
    )

    report = scanner.scan()

    assert len(report.scanner_failures) == 1
    assert report.scanner_failures[0].severity is Severity.CRITICAL


def test_evidence_digest_is_stable_for_equivalent_security_evidence() -> None:
    first = ScannerHarness("security-test")
    first.add_rule("finding", Severity.MEDIUM, lambda _root: "same", "repair")
    second = ScannerHarness("security-test")
    second.add_rule("finding", Severity.MEDIUM, lambda _root: "same", "repair")

    first_report = first.scan()
    second_report = second.scan()

    assert first_report.started_ns != second_report.started_ns or first_report.finished_ns != second_report.finished_ns
    assert first_report.evidence_digest == second_report.evidence_digest


def test_evidence_digest_changes_when_security_evidence_changes() -> None:
    first = ScannerHarness("security-test")
    first.add_rule("finding", Severity.MEDIUM, lambda _root: "first", "repair")
    second = ScannerHarness("security-test")
    second.add_rule("finding", Severity.MEDIUM, lambda _root: "second", "repair")

    assert first.scan().evidence_digest != second.scan().evidence_digest


def test_vuln_scanner_not_run_is_not_clean() -> None:
    scanner = VulnScanner()
    assert scanner.score() == 0.0
    assert scanner.card()["state"] == "not_run"
    assert scanner.card()["complete"] is False
    with pytest.raises(VulnScannerError, match="has not completed"):
        scanner.assert_merge_safe()


@pytest.mark.parametrize("severity", ["unknown", "P0", "", "urgent"])
def test_vuln_scanner_rejects_unknown_severity(severity: str) -> None:
    scanner = VulnScanner()
    with pytest.raises(VulnScannerError, match="severity"):
        scanner.add_rule("custom-rule", severity, lambda _root: None, "repair")


def test_vuln_scanner_rejects_duplicate_rule_name() -> None:
    scanner = VulnScanner()
    with pytest.raises(VulnScannerError, match="duplicate"):
        scanner.add_rule(
            "rbac-missing",
            "high",
            lambda _root: "duplicate",
            "repair",
        )


def test_vuln_scanner_probe_exception_is_redacted_and_blocks_merge() -> None:
    scanner = VulnScanner()
    sensitive_marker = "SENSITIVE_URL_FIXTURE"

    def explode(_root: Path) -> None:
        raise RuntimeError(sensitive_marker)

    scanner.add_rule("custom-explode", "low", explode, "repair")

    card = scanner.scan()

    finding = next(
        item for item in card["findings"] if item["check"] == "custom-explode"
    )
    assert finding["scanner_failure"] is True
    assert finding["severity"] == "critical"
    assert finding["message"] == "scanner rule failed with RuntimeError"
    assert sensitive_marker not in str(card)
    with pytest.raises(VulnScannerError):
        scanner.assert_merge_safe()


def test_vuln_scanner_invalid_output_fails_closed() -> None:
    scanner = VulnScanner()
    scanner.add_rule(
        "non-string",
        "low",
        lambda _root: object(),  # type: ignore[return-value]
        "repair",
    )

    card = scanner.scan()

    finding = next(item for item in card["findings"] if item["check"] == "non-string")
    assert finding["scanner_failure"] is True
    assert finding["severity"] == "critical"


def test_vuln_scanner_oversized_output_fails_closed() -> None:
    scanner = VulnScanner()
    scanner.add_rule(
        "oversized",
        "low",
        lambda _root: "x" * 513,
        "repair",
    )

    card = scanner.scan()

    finding = next(item for item in card["findings"] if item["check"] == "oversized")
    assert finding["scanner_failure"] is True
    assert finding["severity"] == "critical"


def test_vuln_scanner_clean_custom_environment_can_finish() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        state = root / ".skeleton"
        state.mkdir()
        (state / "audit.jsonl").write_text("{}\n", encoding="utf-8")
        (state / "rbac.json").write_text("{}\n", encoding="utf-8")

        scanner = VulnScanner(root)
        with patch.dict(
            os.environ,
            {"SKELETON_MASTER_SECRET": "non-default-secret-value"},
            clear=False,
        ):
            card = scanner.scan()

        assert card["complete"] is True
        assert card["state"] == "complete"
        assert 0.0 <= card["score"] <= 100.0


def test_vuln_scanner_card_counts_scanner_failures_explicitly() -> None:
    scanner = VulnScanner()
    scanner.add_rule(
        "crash",
        "low",
        lambda _root: (_ for _ in ()).throw(OSError("private path")),
        "repair",
    )

    card = scanner.scan()

    assert card["scanner_failures"] >= 1
    assert card["score"] < 100.0
