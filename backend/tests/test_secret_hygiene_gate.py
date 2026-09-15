from __future__ import annotations

import tomllib
from pathlib import Path

from scripts.check_secret_hygiene import violations


REPO_ROOT = Path(__file__).resolve().parents[2]


def _scan(tmp_path: Path, source: str) -> list[str]:
    path = tmp_path / "sample.env"
    path.write_text(source, encoding="utf-8")
    return violations(path)


def test_detects_private_key_material(tmp_path: Path) -> None:
    marker = "-----BEGIN " + "PRIVATE KEY-----"
    findings = _scan(tmp_path, f"KEY={marker}\n")
    assert any("private key" in finding for finding in findings)


def test_detects_github_token_shape(tmp_path: Path) -> None:
    token = "ghp_" + ("A" * 40)
    findings = _scan(tmp_path, f"TOKEN={token}\n")
    assert any("GitHub token" in finding for finding in findings)


def test_detects_gitlab_token_shape(tmp_path: Path) -> None:
    token = "glpat-" + ("A" * 24)
    findings = _scan(tmp_path, f"TOKEN={token}\n")
    assert any("GitLab personal access token" in finding for finding in findings)


def test_detects_npm_token_shape(tmp_path: Path) -> None:
    token = "npm_" + ("A" * 36)
    findings = _scan(tmp_path, f"TOKEN={token}\n")
    assert any("npm access token" in finding for finding in findings)


def test_detects_pypi_token_shape(tmp_path: Path) -> None:
    token = "pypi-" + "AgEIcHlwaS5vcmc" + ("A" * 48)
    findings = _scan(tmp_path, f"TOKEN={token}\n")
    assert any("PyPI API token" in finding for finding in findings)


def test_detects_aws_access_key_shape(tmp_path: Path) -> None:
    key = "AKIA" + ("A" * 16)
    findings = _scan(tmp_path, f"AWS_ACCESS_KEY_ID={key}\n")
    assert any("AWS access key" in finding for finding in findings)


def test_detects_aws_secret_access_key_assignment(tmp_path: Path) -> None:
    key = "A" * 40
    findings = _scan(tmp_path, f"AWS_SECRET_ACCESS_KEY={key}\n")
    assert any("AWS secret access key" in finding for finding in findings)


def test_detects_openai_style_key_shape(tmp_path: Path) -> None:
    key = "sk-" + ("a" * 32)
    findings = _scan(tmp_path, f"API_KEY={key}\n")
    assert any("OpenAI-style API key" in finding for finding in findings)


def test_detects_stripe_live_secret_key(tmp_path: Path) -> None:
    key = "sk_live_" + ("A" * 24)
    findings = _scan(tmp_path, f"STRIPE_SECRET_KEY={key}\n")
    assert any("Stripe live secret key" in finding for finding in findings)


def test_detects_google_api_key(tmp_path: Path) -> None:
    key = "AIza" + ("A" * 35)
    findings = _scan(tmp_path, f"GOOGLE_API_KEY={key}\n")
    assert any("Google API key" in finding for finding in findings)


def test_detects_database_uri_credentials(tmp_path: Path) -> None:
    scheme = "postgresql://"
    credentials = "realuser:" + "realpass123"
    uri = f"{scheme}{credentials}@db.internal/app"
    findings = _scan(tmp_path, f"DATABASE_URL={uri}\n")
    assert any("database URI" in finding for finding in findings)


def test_allows_placeholder_marker_inside_candidate_value(tmp_path: Path) -> None:
    key = "sk-placeholder_example_placeholder_12345"
    findings = _scan(tmp_path, f"OPENAI_API_KEY={key}\n")
    assert findings == []


def test_allows_canonical_database_placeholder_credentials(tmp_path: Path) -> None:
    uri = "postgres://" + "user:pass" + "@db:5432/app"
    findings = _scan(tmp_path, f"DATABASE_URL={uri}\n")
    assert findings == []


def test_placeholder_comment_does_not_suppress_real_secret(tmp_path: Path) -> None:
    key = "sk-" + ("z" * 32)
    findings = _scan(tmp_path, f"OPENAI_API_KEY={key} # placeholder example\n")
    assert any("OpenAI-style API key" in finding for finding in findings)


def test_placeholder_candidate_does_not_hide_second_real_secret(tmp_path: Path) -> None:
    placeholder = "sk-placeholder_example_placeholder_12345"
    real = "sk-" + ("q" * 32)
    findings = _scan(tmp_path, f"FIRST={placeholder} SECOND={real}\n")
    assert any("OpenAI-style API key" in finding for finding in findings)


def test_does_not_echo_secret_value_in_finding(tmp_path: Path) -> None:
    token = "ghp_" + ("B" * 40)
    findings = _scan(tmp_path, f"TOKEN={token}\n")
    assert findings
    assert all(token not in finding for finding in findings)


def test_gitleaks_policy_extends_default_detectors() -> None:
    config = tomllib.loads((REPO_ROOT / ".gitleaks.toml").read_text(encoding="utf-8"))
    assert config["extend"]["useDefault"] is True


def test_secret_scanning_workflow_hardening_contract() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "secret-scanning.yml").read_text(
        encoding="utf-8"
    )
    assert "  pull_request:\n" in workflow
    assert "  push:\n" in workflow
    assert "branches:" not in workflow
    assert "permissions:\n  contents: read\n" in workflow
    assert "persist-credentials: false" in workflow
    assert 'GITLEAKS_VERSION: "8.24.3"' in workflow
    assert 'GITLEAKS_CONFIG: ".gitleaks.toml"' in workflow
    assert 'GITLEAKS_ENABLE_COMMENTS: "false"' in workflow


def test_gitleaks_remains_complementary_to_local_secret_hygiene_gate() -> None:
    precommit = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    hook_start = precommit.index("- id: repository-secret-hygiene")
    hook_end = precommit.index("- id: gitleaks-history", hook_start)
    hook = precommit[hook_start:hook_end]
    assert "check_secret_hygiene.py" in hook
    assert "always_run: true" in hook


def test_full_history_gitleaks_hook_is_manual_and_non_optional() -> None:
    precommit = (REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    hook_start = precommit.index("- id: gitleaks-history")
    hook_end = precommit.index("- id: backend-security-regressions", hook_start)
    hook = precommit[hook_start:hook_end]
    assert "bash scripts/security/run-secret-scan.sh" in hook
    assert "always_run: true" in hook
    assert "stages: [manual]" in hook


def test_local_secret_scan_runner_matches_ci_policy() -> None:
    runner = (REPO_ROOT / "scripts" / "security" / "run-secret-scan.sh").read_text(
        encoding="utf-8"
    )
    assert 'EXPECTED_GITLEAKS_VERSION="8.24.3"' in runner
    assert "python backend/scripts/check_secret_hygiene.py" in runner
    assert "gitleaks git" in runner
    assert "--config=.gitleaks.toml" in runner
    assert "--redact=100" in runner


def test_secret_hygiene_runbook_requires_revocation_and_rescan() -> None:
    runbook = (REPO_ROOT / "docs" / "security" / "SECRET_HYGIENE.md").read_text(
        encoding="utf-8"
    )
    assert "Revoke first" in runbook
    assert "Purge history when required" in runbook
    assert "Invalidate artifacts" in runbook
    assert "Re-scan" in runbook
    assert "Do not paste the credential value" in runbook
    assert "Repository-wide regex exemptions" in runbook
