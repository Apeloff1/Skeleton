from __future__ import annotations

from pathlib import Path
import tempfile
from unittest import mock

from scripts import check_workflow_trigger_fanout as fanout


PROTECTED_DUAL = """name: safe
on:
  pull_request:
  push:
    branches: [main]
permissions: {}
jobs: {}
"""


def _violations(text: str, name: str = "safe.yml") -> list[str]:
    return fanout.violations_from_text(name, text)


def _audit(text: str, name: str = "safe.yml") -> fanout.FanoutAudit:
    return fanout.audit_from_text(name, text)


def test_allows_protected_push_and_pull_request_coverage() -> None:
    audit = _audit(PROTECTED_DUAL)
    assert audit.violations() == []
    assert any(
        finding.run_class == "protected_push_and_pull_request" for finding in audit.findings
    )


def test_allows_inline_event_list_without_push_pr_overlap() -> None:
    text = """name: dispatch-only
on: [workflow_dispatch, schedule]
jobs: {}
"""
    assert _violations(text, "dispatch-only.yml") == []


def test_allows_quoted_on_keys() -> None:
    text = """name: quoted
"on":
  "pull_request":
    "branches": [main]
  "push":
    "branches": [main]
jobs: {}
"""
    assert _violations(text, "quoted.yml") == []


def test_security_workflow_keeps_unconstrained_push_as_coverage() -> None:
    text = """name: secrets
on:
  pull_request:
  push:
  workflow_dispatch:
jobs: {}
"""
    audit = _audit(text, "secret-scanning.yml")
    assert audit.violations() == []
    assert any(
        finding.run_class == "security_every_ref_push_and_pull_request"
        for finding in audit.findings
    )


def test_rejects_unconstrained_push_overlapping_pull_request() -> None:
    text = """name: waste
on:
  pull_request:
  push:
jobs: {}
"""
    findings = _violations(text, "ci-waste.yml")
    assert findings
    assert any("same_repo_head_push_and_pull_request" in finding for finding in findings)
    assert any("trigger-fanout avoidable" in finding for finding in findings)


def test_named_glob_push_is_coverage_not_all_heads() -> None:
    text = """name: frontier
on:
  pull_request:
    branches: [main]
  push:
    branches:
      - 'frontier/**'
jobs: {}
"""
    audit = _audit(text, "frontier-contracts.yml")
    assert audit.violations() == []
    assert any(
        finding.run_class == "named_branch_push_and_pull_request" for finding in audit.findings
    )


def test_rejects_glob_push_overlapping_pull_request() -> None:
    text = """name: waste
on:
  pull_request:
  push:
    branches: ['**']
jobs: {}
"""
    findings = _violations(text, "glob-push.yml")
    assert any("same_repo_head_push_and_pull_request" in finding for finding in findings)


def test_rejects_branches_ignore_push_overlapping_pull_request() -> None:
    text = """name: waste
on:
  pull_request:
  push:
    branches-ignore: [main]
jobs: {}
"""
    findings = _violations(text, "ignore-push.yml")
    assert any("same_repo_head_push_and_pull_request" in finding for finding in findings)


def test_inline_push_and_pull_request_list_is_avoidable() -> None:
    findings = _violations("name: waste\non: [push, pull_request]\njobs: {}\n", "list.yml")
    assert any("same_repo_head_push_and_pull_request" in finding for finding in findings)


def test_flow_mapping_unconstrained_push_is_avoidable() -> None:
    text = "name: waste\non: {push: {}, pull_request: {}}\njobs: {}\n"
    findings = _violations(text, "flow.yml")
    assert any("same_repo_head_push_and_pull_request" in finding for finding in findings)


def test_disjoint_paths_are_not_duplicate_run_classes() -> None:
    text = """name: split
on:
  pull_request:
    paths: [docs/README.md]
  push:
    paths: [backend/app.py]
jobs: {}
"""
    assert _violations(text, "split.yml") == []


def test_review_events_without_dispatcher_are_avoidable() -> None:
    text = """name: ci
on:
  pull_request:
  pull_request_review:
jobs: {}
"""
    findings = _violations(text, "review-ci.yml")
    assert any("review_event_ci_rerun" in finding for finding in findings)


def test_repo_attention_review_events_are_not_avoidable() -> None:
    text = """name: attention
on:
  pull_request:
    types: [edited, synchronize]
  pull_request_review:
    types: [submitted]
  schedule:
    - cron: '17 5 * * *'
jobs:
  sweep:
    if: github.event_name == 'schedule'
"""
    assert _violations(text, "repo-attention.yml") == []


def test_noisy_pr_types_are_estimated_not_violations() -> None:
    text = """name: hygiene
on:
  pull_request:
    types: [opened, synchronize, edited]
jobs: {}
"""
    audit = _audit(text, "pr-hygiene.yml")
    assert audit.violations() == []
    estimated = audit.estimated_avoidable_run_classes()
    assert any(finding.run_class == "metadata_pr_rerun" for finding in estimated)
    assert any("edited" in finding.message for finding in estimated)


def test_schedule_and_push_remain_coverage() -> None:
    text = """name: drain
on:
  schedule:
    - cron: '*/10 * * * *'
  push:
    branches: [main]
jobs: {}
"""
    audit = _audit(text, "queue-drain.yml")
    assert audit.violations() == []
    assert any(finding.run_class == "schedule_and_push_overlap" for finding in audit.findings)


def test_rejects_missing_on_block() -> None:
    findings = _violations("name: unsafe\njobs: {}\n", "unsafe.yml")
    assert any("missing top-level on:" in finding for finding in findings)
    assert any("trigger-fanout opaque" in finding for finding in findings)


def test_rejects_aliased_trigger_configuration() -> None:
    text = """name: unsafe
x-events: &events [push]
on: *events
jobs: {}
"""
    findings = _violations(text, "alias.yml")
    assert any("opaque workflow trigger configuration" in finding for finding in findings)


def test_rejects_tagged_trigger_configuration() -> None:
    findings = _violations("name: unsafe\non: !!seq [push]\njobs: {}\n", "tagged.yml")
    assert any("opaque workflow trigger configuration" in finding for finding in findings)


def test_rejects_merge_key_trigger_configuration() -> None:
    text = """name: unsafe
on:
  <<: {push: {}}
jobs: {}
"""
    findings = _violations(text, "merge.yml")
    assert any("opaque" in finding for finding in findings)


def test_rejects_duplicate_event_keys() -> None:
    text = """name: unsafe
on:
  push:
  push:
jobs: {}
"""
    findings = _violations(text, "dup.yml")
    assert any("duplicate 'push' trigger" in finding for finding in findings)


def test_rejects_unsupported_filter_key() -> None:
    text = """name: unsafe
on:
  push:
    unexpected: [main]
jobs: {}
"""
    findings = _violations(text, "filter.yml")
    assert any("unsupported trigger filter" in finding for finding in findings)


def test_parses_workflow_dispatch_inputs_without_claiming_fanout() -> None:
    text = """name: studio
on:
  workflow_dispatch:
    inputs:
      max_tasks:
        type: string
        default: '2'
  schedule:
    - cron: '19 22,0,2,4 * * *'
jobs: {}
"""
    assert _violations(text, "autonomous-studio.yml") == []


def test_parses_workflow_run_filters() -> None:
    text = """name: intake
on:
  workflow_run:
    workflows:
      - Merge Readiness
      - CI/CD
    types: [completed]
jobs: {}
"""
    record, findings = fanout.parse_triggers_from_text("repair-intake.yml", text)
    assert findings == []
    assert record is not None
    event = record.events[0]
    assert event.name == "workflow_run"
    assert event.types == ("completed",)
    assert event.workflows == ("Merge Readiness", "CI/CD")


def test_current_repository_trigger_fanout_has_no_violations() -> None:
    assert fanout.repository_violations() == []


def test_current_repository_audit_parses_every_workflow() -> None:
    audit = fanout.repository_audit()
    files = fanout.workflow_files()
    assert files
    assert len(audit.records) == len(files)
    assert not any(finding.kind == "opaque" for finding in audit.findings)


def test_prefixes_are_unique_from_concurrency_checker() -> None:
    text = Path(fanout.__file__).read_text(encoding="utf-8")
    assert "check_workflow_concurrency" not in text
    assert "trigger-fanout" in text
    assert fanout.__file__.endswith("check_workflow_trigger_fanout.py")


def test_rejects_symlinked_workflow_file() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        target = root / "target.yml"
        target.write_text(PROTECTED_DUAL, encoding="utf-8")
        link = root / "linked.yml"
        try:
            link.symlink_to(target)
        except (NotImplementedError, OSError) as exc:
            raise AssertionError(f"symlinks unavailable: {type(exc).__name__}") from exc
        findings = fanout.violations(link)
    assert findings == [
        "trigger-fanout opaque opaque_yaml: linked.yml: workflow files must not be symlinks"
    ]


def test_rejects_symlinked_workflow_directory() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        target = root / "real-workflows"
        target.mkdir()
        (target / "safe.yml").write_text(PROTECTED_DUAL, encoding="utf-8")
        link = root / "workflows"
        try:
            link.symlink_to(target, target_is_directory=True)
        except (NotImplementedError, OSError) as exc:
            raise AssertionError(f"directory symlinks unavailable: {type(exc).__name__}") from exc
        assert fanout.repository_violations(link) == [
            "trigger-fanout opaque opaque_yaml: <workflows>: "
            "GitHub Actions workflow directory must not be a symlink"
        ]


def test_read_failure_is_redacted() -> None:
    missing = Path(tempfile.gettempdir()) / "missing-trigger-fanout-workflow.yml"
    findings = fanout.violations(missing)
    assert any("FileNotFoundError" in finding for finding in findings)
    assert not any(str(missing) in finding for finding in findings)


def test_main_fails_closed_when_no_workflows_exist() -> None:
    with tempfile.TemporaryDirectory() as directory:
        with mock.patch.object(fanout, "WORKFLOW_DIR", Path(directory)):
            assert fanout.main() == 1


def test_main_passes_current_repository() -> None:
    assert fanout.main() == 0