from __future__ import annotations

from pathlib import Path

from scripts.check_secret_hygiene import violations


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
    uri = "postgresql://realuser:realpass123@db.internal/app"
    findings = _scan(tmp_path, f"DATABASE_URL={uri}\n")
    assert any("database URI" in finding for finding in findings)


def test_allows_placeholder_marker_inside_candidate_value(tmp_path: Path) -> None:
    key = "sk-placeholder_example_placeholder_12345"
    findings = _scan(tmp_path, f"OPENAI_API_KEY={key}\n")
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
