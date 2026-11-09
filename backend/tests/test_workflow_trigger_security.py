from __future__ import annotations

from pathlib import Path

from scripts.check_workflow_security import violations


def _scan(tmp_path: Path, source: str) -> list[str]:
    path = tmp_path / "workflow.yml"
    path.write_text(source, encoding="utf-8")
    return violations(path)


def test_rejects_inline_event_list_pull_request_target(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: [push, pull_request_target]\npermissions:\n  contents: read\njobs: {}\n",
    )
    assert any("pull_request_target is forbidden" in finding for finding in findings)


def test_rejects_inline_flow_event_mapping_pull_request_target(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: {push: {}, pull_request_target: {}}\npermissions:\n  contents: read\njobs: {}\n",
    )
    assert any("pull_request_target is forbidden" in finding for finding in findings)


def test_rejects_quoted_top_level_on_flow_mapping(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        'name: test\n"on": {"pull_request_target": {}}\npermissions:\n  contents: read\njobs: {}\n',
    )
    assert any("pull_request_target is forbidden" in finding for finding in findings)


def test_rejects_block_sequence_pull_request_target(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non:\n  - push\n  - pull_request_target\npermissions:\n  contents: read\njobs: {}\n",
    )
    assert any("pull_request_target is forbidden" in finding for finding in findings)


def test_allows_nested_branch_filter_named_pull_request_target(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non:\n  push:\n    branches:\n      - pull_request_target\npermissions:\n  contents: read\njobs: {}\n",
    )
    assert findings == []


def test_rejects_aliased_trigger_configuration(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\nx-events: &events [push]\non: *events\npermissions:\n  contents: read\njobs: {}\n",
    )
    assert any("aliased workflow trigger configuration is forbidden" in finding for finding in findings)


def test_rejects_anchored_inline_forbidden_trigger(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: &events [push, pull_request_target]\npermissions:\n  contents: read\njobs: {}\n",
    )
    assert any("pull_request_target is forbidden" in finding for finding in findings)


def test_rejects_tagged_inline_forbidden_trigger(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: !!seq [pull_request_target]\npermissions:\n  contents: read\njobs: {}\n",
    )
    assert any("pull_request_target is forbidden" in finding for finding in findings)


def test_allows_anchored_safe_trigger_list(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "name: test\non: &events [push]\npermissions:\n  contents: read\njobs: {}\n",
    )
    assert findings == []
