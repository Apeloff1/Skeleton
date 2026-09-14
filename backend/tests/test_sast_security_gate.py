from __future__ import annotations

from pathlib import Path

from scripts.check_sast_security import violations


def _scan(tmp_path: Path, source: str) -> list[str]:
    path = tmp_path / "sample.py"
    path.write_text(source, encoding="utf-8")
    return violations(path)


def test_rejects_eval(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "value = eval(user_input)\n")
    assert any("eval() is forbidden" in finding for finding in findings)


def test_rejects_exec(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "exec(user_input)\n")
    assert any("exec() is forbidden" in finding for finding in findings)


def test_rejects_tempfile_mktemp(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import tempfile\npath = tempfile.mktemp()\n")
    assert any("mktemp() is race-prone" in finding for finding in findings)


def test_rejects_requests_verify_false(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import requests\nrequests.get(url, verify=False)\n")
    assert any("verify=False" in finding for finding in findings)


def test_rejects_aliased_httpx_verify_false(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import httpx as hx\nhx.post(url, verify=False)\n")
    assert any("verify=False" in finding for finding in findings)


def test_rejects_httpx_client_with_disabled_verification(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import httpx\nclient = httpx.AsyncClient(verify=False)\n")
    assert any("verify=False" in finding for finding in findings)


def test_rejects_unverified_ssl_context(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import ssl\nctx = ssl._create_unverified_context()\n")
    assert any("disables certificate verification" in finding for finding in findings)


def test_rejects_jwt_signature_verification_disable(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        'import jwt\npayload = jwt.decode(token, options={"verify_signature": False})\n',
    )
    assert any("must not disable signature verification" in finding for finding in findings)


def test_allows_verified_network_request(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import requests\nrequests.get(url, timeout=10)\n")
    assert findings == []
