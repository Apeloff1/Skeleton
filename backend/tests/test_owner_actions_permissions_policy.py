from __future__ import annotations
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
CONFIGURE = ROOT / "scripts" / "configure_actions_permissions.sh"
AUDIT = ROOT / "scripts" / "audit_owner_security_controls.sh"
def test_actions_owner_bootstrap_defaults_to_verification_and_read_only() -> None:
    text = CONFIGURE.read_text(encoding="utf-8")
    assert 'mode="${1:---verify}"' in text
    assert "default_workflow_permissions=read" in text
    assert "can_approve_pull_request_reviews=false" in text
    assert "X-GitHub-Api-Version: 2026-03-10" in text
    assert '.permissions.admin // false' in text
def test_external_control_audit_checks_required_owner_boundaries() -> None:
    text = AUDIT.read_text(encoding="utf-8")
    for marker in ('required_check="Merge Readiness"','required_app_id="15368"','required check is bound to GitHub Actions','protection applies to administrators','pull-request changes are required','force pushes are blocked','branch deletion is blocked','default workflow token permission is read','Actions cannot approve pull requests'):
        assert marker in text
def test_external_control_audit_does_not_query_secret_value_endpoints() -> None:
    text = AUDIT.read_text(encoding="utf-8")
    for endpoint in ("/actions/secrets","/dependabot/secrets","/environments/${","/codespaces/secrets"):
        assert endpoint not in text
    assert "names and protection rule types only" in text or "Deployment environments (names and protection rule types only)" in text
