from __future__ import annotations

from pathlib import Path

from scripts.check_workflow_security import violations


PIN = "11d5960a326750d5838078e36cf38b85af677262"


def _scan(tmp_path: Path, source: str) -> list[str]:
    path = tmp_path / "workflow.yml"
    path.write_text(source, encoding="utf-8")
    return violations(path)


def test_rejects_nonleading_flow_style_mutable_action(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - {name: unsafe, uses: vendor/action@v1}\n",
    )
    assert any("not pinned to a 40-character commit SHA" in finding for finding in findings)


def test_rejects_nonleading_quoted_uses_mutable_action(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        'name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - {name: unsafe, "uses": vendor/action@main}\n',
    )
    assert any("not pinned to a 40-character commit SHA" in finding for finding in findings)


def test_allows_nonleading_flow_style_pinned_action(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - {{name: safe, uses: vendor/action@{PIN}}}\n",
    )
    assert findings == []


def test_rejects_nonleading_flow_checkout_without_credential_hardening(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - {{name: checkout, uses: actions/checkout@{PIN}}}\n",
    )
    assert any("persist-credentials: false" in finding for finding in findings)


def test_allows_nonleading_flow_checkout_with_inline_hardening(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - {{name: checkout, uses: actions/checkout@{PIN}, with: {{persist-credentials: false}}}}\n",
    )
    assert findings == []
