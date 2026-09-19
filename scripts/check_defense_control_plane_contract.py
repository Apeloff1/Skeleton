#!/usr/bin/env python3
"""Fail-closed contract gate for the repository defense and automation planes.

The repository already has many focused scanners. This gate protects the
*composition* of the new controls: emergency holds must execute before token
use, workflow-run authority must be admitted before privileged API access,
cancelled CI tombstones must not allocate an evaluator, new adversarial tests
must remain part of the canonical quality gate, and outbound/incident/scanner
primitives must remain present.

This is intentionally a narrow structural contract, not a replacement for unit
tests or semantic security scanners. It catches accidental security-control
deletion and ordering regressions cheaply before more expensive checks run.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Iterable

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
MAX_CONTROL_FILE_BYTES = 250_000

REQUIRED_FILES = (
    "skeleton/security/scanner_integrity.py",
    "skeleton/security/defense_plane.py",
    "skeleton/security/incident_containment.py",
    "skeleton/security/outbound_url.py",
    "skeleton/automation/control_plane.py",
    "skeleton/pr_automation/safety.py",
    "skeleton/pr_automation/event_firewall.py",
    "skeleton/pr_automation/runner.py",
    ".github/workflows/pr-automation-index.yml",
    "scripts/quality-gates.sh",
)

REQUIRED_TESTS = (
    "skeleton/testing/test_scanner_integrity.py",
    "skeleton/testing/test_defense_plane.py",
    "skeleton/testing/test_defense_control_plane_contract.py",
    "skeleton/testing/test_incident_containment.py",
    "skeleton/testing/test_automation_control_plane.py",
    "skeleton/testing/test_pr_automation_event_firewall.py",
    "skeleton/testing/test_pr_automation_operator_safety.py",
    "skeleton/testing/test_outbound_url_resolution_security.py",
)

OPERATOR_ENV_MARKERS = (
    "SKELETON_AUTOMATION_PAUSED",
    "SKELETON_AUTOMATION_QUARANTINED",
    "SKELETON_AUTOMATION_HOLD_REASON",
)

WORKFLOW_RUN_ENV_MARKERS = (
    "WORKFLOW_RUN_ID",
    "WORKFLOW_RUN_ATTEMPT",
    "WORKFLOW_RUN_WORKFLOW_ID",
    "WORKFLOW_RUN_NAME",
    "WORKFLOW_RUN_STATUS",
    "WORKFLOW_RUN_CONCLUSION",
    "WORKFLOW_RUN_EVENT",
    "WORKFLOW_RUN_HEAD_REPOSITORY",
    "WORKFLOW_RUN_HEAD_SHA",
    "WORKFLOW_RUN_HEAD_REF",
    "WORKFLOW_RUN_PR_HINTS",
)


@dataclass(frozen=True, slots=True)
class Finding:
    path: str
    code: str
    message: str

    def render(self) -> str:
        return f"defense-contract {self.code}: {self.path}: {self.message}"


def _read_control(root: Path, relative: str) -> tuple[str | None, list[Finding]]:
    path = root / relative
    findings: list[Finding] = []
    try:
        if path.is_symlink():
            findings.append(
                Finding(relative, "symlink", "security control file must not be a symlink")
            )
            return None, findings
        stat = path.stat()
        if not path.is_file():
            findings.append(
                Finding(relative, "missing", "required security control file is absent")
            )
            return None, findings
        if stat.st_size > MAX_CONTROL_FILE_BYTES:
            findings.append(
                Finding(
                    relative,
                    "oversized",
                    f"security control exceeds {MAX_CONTROL_FILE_BYTES} bytes",
                )
            )
            return None, findings
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        findings.append(
            Finding(
                relative,
                "unreadable",
                f"cannot read security control ({type(exc).__name__})",
            )
        )
        return None, findings
    if "\x00" in text:
        findings.append(
            Finding(relative, "binary", "security control contains NUL bytes")
        )
        return None, findings
    return text, findings


def _require(
    findings: list[Finding],
    *,
    path: str,
    text: str,
    marker: str,
    code: str,
    message: str,
) -> None:
    if marker not in text:
        findings.append(Finding(path, code, message))


def _require_before(
    findings: list[Finding],
    *,
    path: str,
    text: str,
    first: str,
    second: str,
    code: str,
    message: str,
) -> None:
    first_pos = text.find(first)
    second_pos = text.find(second)
    if first_pos < 0 or second_pos < 0 or first_pos >= second_pos:
        findings.append(Finding(path, code, message))


def _require_all(
    findings: list[Finding],
    *,
    path: str,
    text: str,
    markers: Iterable[str],
    code: str,
    label: str,
) -> None:
    for marker in markers:
        if marker not in text:
            findings.append(
                Finding(path, code, f"missing {label}: {marker}")
            )


def audit(root: Path = DEFAULT_ROOT) -> list[Finding]:
    findings: list[Finding] = []
    texts: dict[str, str] = {}

    for relative in (*REQUIRED_FILES, *REQUIRED_TESTS):
        text, file_findings = _read_control(root, relative)
        findings.extend(file_findings)
        if text is not None:
            texts[relative] = text

    runner_path = "skeleton/pr_automation/runner.py"
    runner = texts.get(runner_path)
    if runner is not None:
        _require_all(
            findings,
            path=runner_path,
            text=runner,
            markers=(
                "from .event_firewall import admit_workflow_run, event_from_env",
                "from .safety import load_operator_safety",
                "safety = load_operator_safety()",
                "if safety.blocked:",
                "event = event_from_env(",
                "admission = admit_workflow_run(event)",
                "if admission.dropped:",
                "if admission is not None and not admission.mutation_authorized:",
                "mode = Mode.OBSERVE",
            ),
            code="runner-boundary",
            label="privileged runner boundary",
        )
        token_marker = 'token = os.getenv("GITHUB_TOKEN", "")'
        for marker, label in (
            ("safety = load_operator_safety()", "operator safety"),
            ("if safety.blocked:", "operator hold"),
            ("event = event_from_env(", "workflow event parsing"),
            ("admission = admit_workflow_run(event)", "workflow event admission"),
            ("if admission.dropped:", "workflow event drop"),
        ):
            _require_before(
                findings,
                path=runner_path,
                text=runner,
                first=marker,
                second=token_marker,
                code="token-order",
                message=f"{label} must execute before GitHub token access",
            )

    workflow_path = ".github/workflows/pr-automation-index.yml"
    workflow = texts.get(workflow_path)
    if workflow is not None:
        _require_all(
            findings,
            path=workflow_path,
            text=workflow,
            markers=OPERATOR_ENV_MARKERS,
            code="operator-env",
            label="operator safety variable",
        )
        _require_all(
            findings,
            path=workflow_path,
            text=workflow,
            markers=WORKFLOW_RUN_ENV_MARKERS,
            code="workflow-authority-env",
            label="workflow-run authority variable",
        )
        _require(
            findings,
            path=workflow_path,
            text=workflow,
            marker="github.event.workflow_run.conclusion != 'cancelled'",
            code="cancelled-tombstone",
            message="cancelled upstream runs must be skipped before evaluator allocation",
        )
        _require(
            findings,
            path=workflow_path,
            text=workflow,
            marker='cp -R skeleton/pr_automation "$trusted_root/pr_automation"',
            code="trusted-stage",
            message="privileged PR automation must execute staged default-branch package",
        )
        _require(
            findings,
            path=workflow_path,
            text=workflow,
            marker="python -I -c",
            code="isolated-python",
            message="privileged PR automation must run Python in isolated mode",
        )
        _require(
            findings,
            path=workflow_path,
            text=workflow,
            marker="persist-credentials: false",
            code="checkout-credentials",
            message="trusted checkout must not persist Git credentials",
        )

    safety_path = "skeleton/pr_automation/safety.py"
    safety = texts.get(safety_path)
    if safety is not None:
        _require_all(
            findings,
            path=safety_path,
            text=safety,
            markers=(
                "class OperatorSafetyError",
                "class OperatorSafety:",
                "def load_operator_safety(",
                "raise OperatorSafetyError",
                "quarantined",
                "paused",
            ),
            code="operator-safety",
            label="operator safety primitive",
        )

    firewall_path = "skeleton/pr_automation/event_firewall.py"
    firewall = texts.get(firewall_path)
    if firewall is not None:
        _require_all(
            findings,
            path=firewall_path,
            text=firewall,
            markers=(
                "class AdmissionLevel",
                'DROP = "drop"',
                'OBSERVE = "observe"',
                'MUTATE = "mutate"',
                'frozenset({"Merge Readiness"})',
                'event.conclusion == "cancelled"',
                'event.conclusion != "success"',
                "event.source_event not in selected.mutation_source_events",
                "cross-repository completion is observation-only",
            ),
            code="event-firewall",
            label="workflow event admission invariant",
        )

    automation_path = "skeleton/automation/control_plane.py"
    automation = texts.get(automation_path)
    if automation is not None:
        _require_all(
            findings,
            path=automation_path,
            text=automation,
            markers=(
                "class PermitAuthority",
                "hmac.compare_digest",
                "class PermitUseLedger",
                "class MutationBudget",
                "class CircuitBreaker",
                "class AutomationControlPlane",
                "destructive automation is disabled by policy",
                "repository defense plane denied automation request",
            ),
            code="automation-control",
            label="automation authority invariant",
        )

    defense_path = "skeleton/security/defense_plane.py"
    defense = texts.get(defense_path)
    if defense is not None:
        _require_all(
            findings,
            path=defense_path,
            text=defense,
            markers=(
                "class ContainmentMode",
                'LOCKDOWN = "lockdown"',
                "class ReplayWindow",
                "class SlidingWindowBudget",
                "class QuarantineRegistry",
                "class IntegrityLedger",
                "class DefensePlane",
                "request metadata attempts to alter its own authority",
                "only observation is permitted in lockdown mode",
            ),
            code="defense-plane",
            label="defense-plane invariant",
        )

    incident_path = "skeleton/security/incident_containment.py"
    incident = texts.get(incident_path)
    if incident is not None:
        _require_all(
            findings,
            path=incident_path,
            text=incident,
            markers=(
                "class IncidentCoordinator",
                "class RecoveryAuthority",
                "hmac.compare_digest",
                "another active incident requires stronger containment",
                "recovery token has already been consumed",
                "incident must pass through authenticated recovery before closure",
            ),
            code="incident-containment",
            label="incident recovery invariant",
        )

    scanner_path = "skeleton/security/scanner_integrity.py"
    scanner = texts.get(scanner_path)
    if scanner is not None:
        _require_all(
            findings,
            path=scanner_path,
            text=scanner,
            markers=(
                "class ScannerHarness",
                "scanner_failure=True",
                "security scan evidence is incomplete",
                "security scanner self-failure detected",
                "blocking security findings detected",
            ),
            code="scanner-integrity",
            label="scanner integrity invariant",
        )

    legacy_scanner_path = "skeleton/security/vuln_scanner.py"
    legacy_scanner = texts.get(legacy_scanner_path)
    if legacy_scanner is not None:
        _require_all(
            findings,
            path=legacy_scanner_path,
            text=legacy_scanner,
            markers=(
                "if not self._has_scanned:",
                "return 0.0",
                "scanner rule failed with",
                "scanner_failure=True",
                "severity must be one of:",
            ),
            code="legacy-scanner",
            label="legacy scanner fail-closed invariant",
        )

    outbound_path = "skeleton/security/outbound_url.py"
    outbound = texts.get(outbound_path)
    if outbound is not None:
        _require_all(
            findings,
            path=outbound_path,
            text=outbound,
            markers=(
                "class ResolvedDestination",
                "def resolve_public_https_url(",
                "DNS resolution includes non-public address",
                "def validate_connected_peer(",
                "does not match approved DNS evidence",
                "def validate_public_https_redirect(",
            ),
            code="outbound-boundary",
            label="outbound network invariant",
        )

    gate_path = "scripts/quality-gates.sh"
    gate = texts.get(gate_path)
    if gate is not None:
        _require_all(
            findings,
            path=gate_path,
            text=gate,
            markers=REQUIRED_TESTS,
            code="quality-gate-tests",
            label="canonical defense regression",
        )
        _require(
            findings,
            path=gate_path,
            text=gate,
            marker="python scripts/check_defense_control_plane_contract.py",
            code="quality-gate-contract",
            message="canonical quality gate must execute defense contract checker",
        )

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check defense and automation control-plane structural invariants."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="repository root to audit",
    )
    args = parser.parse_args(argv)

    findings = audit(args.root)
    for finding in findings:
        print(finding.render(), file=sys.stderr)
    if findings:
        print(
            f"defense-contract: FAIL ({len(findings)} finding(s))",
            file=sys.stderr,
        )
        return 1
    print("defense-contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
