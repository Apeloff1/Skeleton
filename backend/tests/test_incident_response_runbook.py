from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = REPO_ROOT / "docs" / "SECURITY_INCIDENT_RESPONSE.md"


def _runbook() -> str:
    return RUNBOOK.read_text(encoding="utf-8")


def test_runbook_exists_and_defines_operational_severity() -> None:
    text = _runbook()
    assert "SEV-1 / critical" in text
    assert "SEV-2 / high" in text
    assert "SEV-3 / moderate" in text
    assert "Mandatory rollback triggers" in text


def test_runbook_links_canonical_repository_gates() -> None:
    text = _runbook()
    required = (
        "bash scripts/quality-gates.sh",
        ".github/workflows/backend-quality.yml",
        ".github/workflows/secret-scanning.yml",
        ".github/workflows/dependency-security.yml",
        "python backend/scripts/check_secret_hygiene.py",
        "python backend/scripts/check_workflow_security.py",
        "python backend/scripts/check_process_safety.py",
        "python backend/scripts/check_deserialization_safety.py",
        "python backend/scripts/check_sast_security.py",
        "python backend/scripts/check_js_process_alias_safety.py",
        "backend/tests/test_api_middleware_adversarial.py",
    )
    for value in required:
        assert value in text


def test_runbook_covers_high_risk_incident_classes() -> None:
    text = _runbook()
    headings = (
        "Suspected credential or secret exposure",
        "Proxy, forwarded-IP, and request-identity incident",
        "Rate-limit abuse or saturation",
        "Dependency or supply-chain alert",
        "Compromised CI or workflow configuration",
        "Unsafe process execution, deserialization, or SAST finding",
        "Availability or failed-deploy incident",
        "Evidence preservation",
        "Recovery exit criteria",
        "Post-incident review template",
    )
    for heading in headings:
        assert heading in text


def test_runbook_forbids_unsafe_incident_shortcuts() -> None:
    text = _runbook()
    assert "Never copy a real secret into the incident record" in text
    assert "do not invent one during an incident" in text
    assert "Do not weaken a scanner to make the build green" in text
    assert "Do not widen `TRUSTED_PROXY_CIDRS` merely to make traffic pass" in text
    assert "Do not respond to saturation by setting unbounded state" in text


def test_runbook_requires_evidence_and_post_recovery_validation() -> None:
    text = _runbook()
    assert "Preserve original logs and artifacts" in text
    assert "Record hashes when practical" in text
    assert "A production recovery is not complete" in text
    assert "SEV-1 and SEV-2 incidents require a written post-incident review" in text
    assert "Non-production drill" in text
