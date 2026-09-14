from __future__ import annotations

from pathlib import Path

from scripts.check_workflow_security import violations


PIN = "11d5960a326750d5838078e36cf38b85af677262"


def _scan(tmp_path: Path, source: str) -> list[str]:
    path = tmp_path / "workflow.yml"
    path.write_text(source, encoding="utf-8")
    return violations(path)


def test_accepts_sha_pinned_action_and_read_permissions(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@{PIN}\n",
    )
    assert findings == []


def test_rejects_tag_pinned_action(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@v4\n",
    )
    assert any("not pinned to a 40-character commit SHA" in finding for finding in findings)


def test_rejects_unversioned_action(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - uses: vendor/action\n",
    )
    assert any("must be pinned" in finding for finding in findings)


def test_allows_local_actions(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions:\n  contents: read\njobs:\n  test:\n    steps:\n      - uses: ./.github/actions/local\n",
    )
    assert findings == []


def test_rejects_missing_top_level_permissions(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        f"name: test\non: [push]\njobs:\n  test:\n    steps:\n      - uses: actions/checkout@{PIN}\n",
    )
    assert any("missing explicit top-level permissions" in finding for finding in findings)


def test_rejects_pull_request_target(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non:\n  pull_request_target:\npermissions:\n  contents: read\njobs: {}\n",
    )
    assert any("pull_request_target is forbidden" in finding for finding in findings)


def test_rejects_write_all_permissions(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push]\npermissions: write-all\njobs: {}\n",
    )
    assert any("write permissions are forbidden" in finding or "write-all" in finding for finding in findings)
