from __future__ import annotations

from pathlib import Path

from scripts.check_workflow_security import violations


PIN = "11d5960a326750d5838078e36cf38b85af677262"


def _scan(tmp_path: Path, source: str) -> list[str]:
    path = tmp_path / "workflow.yml"
    path.write_text(source, encoding="utf-8")
    return violations(path)


def test_rejects_quoted_uses_mutable_action(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        'name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - "uses": vendor/action@v1\n',
    )
    assert any("not pinned to a 40-character commit SHA" in finding for finding in findings)


def test_allows_quoted_uses_sha_pinned_action(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - 'uses': vendor/action@{PIN}\n",
    )
    assert findings == []


def test_allows_quoted_checkout_hardening(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f'name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - "uses": actions/checkout@{PIN}\n        with:\n          \'persist-credentials\': false\n',
    )
    assert findings == []


def test_rejects_quoted_workflow_write_scope(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        'name: test\non: [push]\npermissions:\n  "contents": write\njobs:\n  test:\n    steps:\n      - run: echo safe\n',
    )
    assert any("workflow-wide contents: write is forbidden" in finding for finding in findings)


def test_rejects_quoted_pull_request_target(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        'name: test\non:\n  "pull_request_target":\npermissions:\n  contents: read\njobs: {}\n',
    )
    assert any("pull_request_target is forbidden" in finding for finding in findings)
