from __future__ import annotations

from pathlib import Path
import tempfile
from unittest import mock

from scripts import check_workflow_concurrency as concurrency


SAFE_WORKFLOW = """name: safe
on:
  pull_request:
  push:
    branches: [main]
concurrency:
  group: safe-gate-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
permissions: {}
jobs: {}
"""


def _scan(text: str, name: str = "safe.yml") -> list[str]:
    _record, findings = concurrency.violations_from_text(name, text)
    return findings


def test_allows_unique_pr_number_or_ref_group() -> None:
    assert _scan(SAFE_WORKFLOW) == []


def test_allows_pr_number_only_when_workflow_is_pull_request_only() -> None:
    text = """name: hygiene
on:
  pull_request:
concurrency:
  group: pr-hygiene-${{ github.event.pull_request.number }}
  cancel-in-progress: true
jobs: {}
"""
    assert _scan(text, "pr-hygiene.yml") == []


def test_allows_issue_or_pr_number_with_literal_sweep_fallback() -> None:
    text = """name: attention
on:
  issues:
  pull_request:
  schedule:
    - cron: '0 0 * * *'
concurrency:
  group: repository-attention-${{ github.event.issue.number || github.event.pull_request.number || 'sweep' }}
  cancel-in-progress: false
jobs: {}
"""
    assert _scan(text, "repo-attention.yml") == []


def test_allows_branch_fallback_when_event_name_discriminates() -> None:
    text = """name: drain
on:
  workflow_run:
  schedule:
  push:
concurrency:
  group: pr-run-drain-${{ github.event_name }}-${{ github.event.workflow_run.head_branch || github.ref_name }}
  cancel-in-progress: ${{ github.event_name == 'workflow_run' }}
jobs: {}
"""
    assert _scan(text, "pr-obsolete-run-drain.yml") == []


def test_rejects_missing_concurrency() -> None:
    text = """name: unsafe
on:
  pull_request:
  push:
permissions: {}
jobs: {}
"""
    findings = _scan(text, "unsafe.yml")
    assert any("missing top-level concurrency" in finding for finding in findings)


def test_rejects_inline_concurrency_mapping() -> None:
    text = """name: unsafe
on: [push]
concurrency: {group: unsafe, cancel-in-progress: true}
jobs: {}
"""
    findings = _scan(text, "unsafe.yml")
    assert any("opaque/inline concurrency" in finding for finding in findings)


def test_rejects_number_or_ref_name_collision() -> None:
    text = """name: unsafe
on:
  pull_request:
  push:
concurrency:
  group: unsafe-${{ github.event.pull_request.number || github.ref_name }}
  cancel-in-progress: true
jobs: {}
"""
    findings = _scan(text, "unsafe.yml")
    assert any("PR 123 and branch 123" in finding for finding in findings)


def test_rejects_pr_number_without_fallback_on_mixed_triggers() -> None:
    text = """name: unsafe
on:
  pull_request:
  push:
concurrency:
  group: unsafe-${{ github.event.pull_request.number }}
  cancel-in-progress: true
jobs: {}
"""
    findings = _scan(text, "unsafe.yml")
    assert any("without a safe fallback" in finding for finding in findings)


def test_rejects_issue_number_on_pull_request_without_pr_fallback() -> None:
    text = """name: unsafe
on:
  pull_request:
concurrency:
  group: unsafe-${{ github.event.issue.number }}
  cancel-in-progress: true
jobs: {}
"""
    findings = _scan(text, "unsafe.yml")
    assert any("pull_request runs do not populate github.event.issue.number" in finding for finding in findings)


def test_rejects_branch_name_fallback_without_event_name() -> None:
    text = """name: unsafe
on:
  workflow_run:
  schedule:
concurrency:
  group: unsafe-${{ github.event.workflow_run.head_branch || github.ref_name }}
  cancel-in-progress: false
jobs: {}
"""
    findings = _scan(text, "unsafe.yml")
    assert any("github.event_name" in finding for finding in findings)


def test_rejects_expression_only_group_without_literal_prefix() -> None:
    text = """name: unsafe
on: [push]
concurrency:
  group: ${{ github.ref }}
  cancel-in-progress: true
jobs: {}
"""
    findings = _scan(text, "unsafe.yml")
    assert any("unique literal workflow identity prefix" in finding for finding in findings)


def test_rejects_aliased_trigger_configuration() -> None:
    text = """name: unsafe
x-events: &events [push]
on: *events
concurrency:
  group: unsafe-gate
  cancel-in-progress: false
jobs: {}
"""
    findings = _scan(text, "unsafe.yml")
    assert any("opaque workflow trigger configuration" in finding for finding in findings)


def test_rejects_opaque_group_expression() -> None:
    text = """name: unsafe
on: [push]
concurrency:
  group: unsafe-${{ format('{0}', github.ref) }}
  cancel-in-progress: true
jobs: {}
"""
    findings = _scan(text, "unsafe.yml")
    assert any("opaque concurrency group expression" in finding for finding in findings)


def test_rejects_missing_cancel_in_progress() -> None:
    text = """name: unsafe
on: [push]
concurrency:
  group: unsafe-gate
jobs: {}
"""
    findings = _scan(text, "unsafe.yml")
    assert any("cancel-in-progress" in finding for finding in findings)


def test_quoted_concurrency_keys_are_inspected() -> None:
    text = """name: quoted
"on":
  "push":
"concurrency":
  "group": quoted-gate-${{ github.ref }}
  "cancel-in-progress": false
jobs: {}
"""
    assert _scan(text, "quoted.yml") == []


def test_current_repository_concurrency_groups_pass() -> None:
    assert concurrency.repository_violations() == []


def test_legacy_merge_readiness_drain_has_unique_top_level_concurrency() -> None:
    workflow = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "merge-readiness-concurrency-drain.yml"
    ).read_text(encoding="utf-8")

    record, findings = concurrency.violations_from_text(
        "merge-readiness-concurrency-drain.yml",
        workflow,
    )
    assert findings == []
    assert record is not None
    assert record.prefix == "merge-readiness-legacy-drain-"


def test_shared_prefix_across_workflows_is_a_collision() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        (root / "one.yml").write_text(
            "name: one\non: [push]\nconcurrency:\n  group: shared-${{ github.ref }}\n  cancel-in-progress: true\njobs: {}\n",
            encoding="utf-8",
        )
        (root / "two.yml").write_text(
            "name: two\non: [push]\nconcurrency:\n  group: shared-${{ github.sha }}\n  cancel-in-progress: true\njobs: {}\n",
            encoding="utf-8",
        )
        findings = concurrency.repository_violations(root)
    assert any("prefix 'shared-' is shared by one.yml, two.yml" in finding for finding in findings)


def test_rejects_symlinked_workflow_file() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        target = root / "target.yml"
        target.write_text(SAFE_WORKFLOW, encoding="utf-8")
        link = root / "linked.yml"
        try:
            link.symlink_to(target)
        except (NotImplementedError, OSError) as exc:
            raise AssertionError(f"symlinks unavailable: {type(exc).__name__}") from exc
        _record, findings = concurrency.violations(link)
    assert findings == ["linked.yml: workflow files must not be symlinks"]


def test_rejects_symlinked_workflow_directory() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        target = root / "real-workflows"
        target.mkdir()
        (target / "safe.yml").write_text(SAFE_WORKFLOW, encoding="utf-8")
        link = root / "workflows"
        try:
            link.symlink_to(target, target_is_directory=True)
        except (NotImplementedError, OSError) as exc:
            raise AssertionError(f"directory symlinks unavailable: {type(exc).__name__}") from exc
        assert concurrency.repository_violations(link) == [
            "GitHub Actions workflow directory must not be a symlink"
        ]


def test_read_failure_is_redacted() -> None:
    missing = Path(tempfile.gettempdir()) / "missing-concurrency-workflow.yml"
    _record, findings = concurrency.violations(missing)
    assert any("FileNotFoundError" in finding for finding in findings)
    assert not any(str(missing) in finding for finding in findings)


def test_main_fails_closed_when_no_workflows_exist() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with mock.patch.object(concurrency, "WORKFLOW_DIR", Path(directory)):
            assert concurrency.main() == 1
