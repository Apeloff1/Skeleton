from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SECURITY_POLICY = REPO_ROOT / "docs" / "SECURITY_CI_POLICY.md"
REQUIRED_CHECKS = REPO_ROOT / "docs" / "CI_REQUIRED_CHECKS.md"


def test_required_checks_security_policy_link_resolves() -> None:
    required_checks = REQUIRED_CHECKS.read_text(encoding="utf-8")

    assert "docs/SECURITY_CI_POLICY.md" in required_checks
    assert SECURITY_POLICY.is_file()


def test_security_policy_keeps_operational_contract_sections() -> None:
    policy = SECURITY_POLICY.read_text(encoding="utf-8")

    required_sections = (
        "## Security ownership",
        "## Threat model",
        "## CI security controls",
        "## Temporary exceptions",
        "## Emergency merge override",
        "## Credential rotation and revocation",
        "## Incident response",
        "## Sensitive output and redaction",
        "## Residual and admin-only risks",
    )

    for section in required_sections:
        assert section in policy, f"missing security policy section: {section}"


def test_security_policy_keeps_fail_closed_and_admin_boundary_language() -> None:
    policy = SECURITY_POLICY.read_text(encoding="utf-8").lower()

    assert "fail closed" in policy
    assert "branch protection" in policy
    assert "merge readiness" in policy
    assert "provider-side revocation" in policy
