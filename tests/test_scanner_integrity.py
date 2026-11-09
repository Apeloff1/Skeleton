from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.security.scanner_integrity import (
    RuleResult,
    ScanState,
    ScannerHarness,
    ScannerIntegrityError,
    Severity,
)
from skeleton.security.vuln_scanner import VulnScanner, VulnScannerError


def test_harness_refuses_score_before_scan() -> None:
    scanner = ScannerHarness("security-test")
    scanner.add_rule("clean", Severity.LOW, lambda _root: None, "fix")
    with pytest.raises(ScannerIntegrityError, match="has not run"):
        scanner.score()


def test_harness_turns_probe_crash_into_critical_self_failure() -> None:
    def explode(_root: Path):
        raise RuntimeError("secret-token-should-not-leak")

    scanner = ScannerHarness("security-test")
    scanner.add_rule("explode", Severity.LOW, explode, "repair scanner")
    report = scanner.scan()

    assert report.state is ScanState.COMPLETE
    assert report.score() == 60.0
    assert len(report.scanner_failures) == 1
    finding = report.scanner_failures[0]
    assert finding.severity is Severity.CRITICAL
    assert "RuntimeError" in finding.message
    assert "secret-token-should-not-leak" not in finding.message
    with pytest.raises(ScannerIntegrityError):
        report.assert_merge_safe()


def test_harness_rejects_duplicate_rules_and_unknown_severity() -> None:
    scanner = ScannerHarness("security-test")
    scanner.add_rule("one", "low", lambda _root: None, "fix")
    with pytest.raises(ScannerIntegrityError, match="duplicate"):
        scanner.add_rule("one", "low", lambda _root: None, "fix")
    with pytest.raises(ValueError):
        scanner.add_rule("two", "catastrophic", lambda _root: None, "fix")


def test_harness_structured_result_can_raise_severity() -> None:
    scanner = ScannerHarness("security-test")
    scanner.add_rule(
        "structured",
        Severity.LOW,
        lambda _root: RuleResult(
            "danger",
            remediation="block",
            severity=Severity.HIGH,
            metadata=(("source", "fixture"),),
        ),
        "default",
    )
    report = scanner.scan()
    assert report.findings[0].severity is Severity.HIGH
    assert report.findings[0].metadata == (("source", "fixture"),)


def test_harness_evidence_digest_is_stable_for_equivalent_results() -> None:
    first = ScannerHarness("security-test")
    second = ScannerHarness("security-test")
    for scanner in (first, second):
        scanner.add_rule("clean", Severity.LOW, lambda _root: None, "fix")
        scanner.add_rule("finding", Severity.MEDIUM, lambda _root: "issue", "repair")
    assert first.scan().evidence_digest == second.scan().evidence_digest


def test_legacy_vuln_scanner_is_not_clean_before_scan() -> None:
    scanner = VulnScanner()
    assert scanner.score() == 0.0
    assert scanner.card()["state"] == "not_run"
    with pytest.raises(VulnScannerError, match="has not completed"):
        scanner.assert_merge_safe()


def test_legacy_vuln_scanner_probe_crash_is_redacted_and_blocking(tmp_path: Path) -> None:
    scanner = VulnScanner(tmp_path)
    scanner._rules.clear()
    scanner.add_rule(
        "crash",
        "low",
        lambda _root: (_ for _ in ()).throw(RuntimeError("Bearer secret-value")),
        "repair",
    )
    card = scanner.scan()
    assert card["complete"] is True
    assert card["scanner_failures"] == 1
    assert card["score"] == 60.0
    assert "RuntimeError" in card["findings"][0]["message"]
    assert "secret-value" not in card["findings"][0]["message"]
    with pytest.raises(VulnScannerError, match="self-failure"):
        scanner.assert_merge_safe()


def test_legacy_vuln_scanner_rejects_unknown_severity() -> None:
    scanner = VulnScanner()
    with pytest.raises(VulnScannerError):
        scanner.add_rule("bad", "unknown", lambda _root: None, "repair")
