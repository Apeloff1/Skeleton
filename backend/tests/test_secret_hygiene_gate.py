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


def test_detects_openai_style_key_shape(tmp_path: Path) -> None:
    key = "sk-" + ("a" * 32)
    findings = _scan(tmp_path, f"API_KEY={key}\n")
    assert any("OpenAI-style API key" in finding for finding in findings)


def test_detects_database_uri_credentials(tmp_path: Path) -> None:
    uri = "postgresql://realuser:realpass123@db.internal/app"
    findings = _scan(tmp_path, f"DATABASE_URL={uri}\n")
    assert any("database URI" in finding for finding in findings)


def test_allows_explicit_placeholder_examples(tmp_path: Path) -> None:
    key = "sk-" + ("x" * 32)
    findings = _scan(tmp_path, f"OPENAI_API_KEY={key} # placeholder example\n")
    assert findings == []


def test_does_not_echo_secret_value_in_finding(tmp_path: Path) -> None:
    token = "ghp_" + ("B" * 40)
    findings = _scan(tmp_path, f"TOKEN={token}\n")
    assert findings
    assert all(token not in finding for finding in findings)
