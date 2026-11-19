from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "container-digest-refresh.yml"


def text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_digest_refresh_workflow_exists() -> None:
    assert WORKFLOW.is_file()


def test_digest_refresh_is_schedule_and_manual_only() -> None:
    value = text()
    assert "schedule:" in value
    assert 'cron: "31 5 * * 2"' in value
    assert "workflow_dispatch:" in value
    assert "pull_request:" not in value
    assert re.search(r"(?m)^\s*push\s*:", value) is None


def test_digest_refresh_job_is_default_branch_guarded() -> None:
    value = text()
    assert "github.event.repository.default_branch" in value
    assert "refs/heads/{0}" in value


def test_digest_refresh_has_read_only_repository_permissions() -> None:
    value = text()
    permissions = value.split("permissions:", 1)[1].split("concurrency:", 1)[0]
    assert "contents: read" in permissions
    assert "contents: write" not in permissions
    assert "pull-requests: write" not in permissions
    assert "actions: write" not in permissions
    assert "issues: write" not in permissions


def test_checkout_is_immutable_and_does_not_persist_credentials() -> None:
    value = text()
    assert "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" in value
    assert "persist-credentials: false" in value


def test_python_setup_is_immutable() -> None:
    assert "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97" in text()


def test_artifact_upload_is_immutable() -> None:
    assert "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a" in text()


def test_digest_refresh_uses_all_state_machine_phases() -> None:
    value = text()
    for command in ("inventory", "queries", "resolutions", "plan", "apply", "verify"):
        assert f"container_digest_refresh.py {command}" in value


def test_registry_resolution_uses_authoritative_descriptor_digest() -> None:
    value = text()
    assert "docker buildx imagetools inspect" in value
    assert "--format '{{json .Manifest}}'" in value
    assert ".digest | strings" in value
    assert 'test("^sha256:[0-9a-f]{64}$")' in value
    assert "sha256sum" not in value
    assert "--resolver docker-buildx-imagetools-manifest-digest" in value
    assert "docker-buildx-imagetools-raw-sha256" not in value


def test_refresh_source_commit_comes_from_trusted_event_context_via_env() -> None:
    value = text()
    assert "SOURCE_COMMIT: ${{ github.sha }}" in value
    assert '--source-commit "$SOURCE_COMMIT"' in value
    assert "--source-commit ${{ github.sha }}" not in value


def test_refresh_does_not_receive_untrusted_dispatch_inputs() -> None:
    value = text()
    assert "github.event.inputs" not in value
    assert "inputs." not in value


def test_refresh_does_not_push_or_create_pr() -> None:
    value = text()
    forbidden = (
        "git push",
        "gh pr create",
        "pulls.create",
        "create-pull-request",
        "contents: write",
        "pull-requests: write",
    )
    for marker in forbidden:
        assert marker not in value


def test_refresh_publishes_patch_and_provenance_artifacts() -> None:
    value = text()
    for name in (
        "container-inventory.json",
        "container-resolutions.json",
        "container-refresh-plan.json",
        "container-refresh-evidence.json",
        "container-refresh.patch",
    ):
        assert name in value


def test_artifact_upload_fails_closed_and_is_retained() -> None:
    value = text()
    assert "if-no-files-found: error" in value
    assert "retention-days: 30" in value


def test_refresh_has_bounded_runtime() -> None:
    value = text()
    assert "timeout-minutes: 30" in value


def test_refresh_has_ref_scoped_concurrency() -> None:
    value = text()
    assert "group: container-digest-refresh-${{ github.ref }}" in value
    assert "cancel-in-progress: true" in value


def test_resolver_loop_is_fail_fast() -> None:
    value = text()
    assert "set -euo pipefail" in value


def test_resolver_consumes_validated_queries_file() -> None:
    value = text()
    assert 'done < "$RUNNER_TEMP/container-queries.txt"' in value


def test_apply_is_followed_by_verify_before_patch_generation() -> None:
    value = text()
    apply_pos = value.index("container_digest_refresh.py apply")
    verify_pos = value.index("container_digest_refresh.py verify")
    patch_pos = value.index("git diff --no-ext-diff --binary")
    assert apply_pos < verify_pos < patch_pos


def test_summary_declares_read_only_review_boundary() -> None:
    value = text()
    assert "workflow is read-only to GitHub" in value
    assert "Apply the retained patch only after review" in value


def test_no_secret_context_is_used() -> None:
    value = text()
    assert "${{ secrets." not in value
    assert "github.token" not in value
    assert "GH_TOKEN" not in value


def test_workflow_has_no_mutable_action_tags() -> None:
    value = text()
    uses_lines = [
        line.strip()
        for line in value.splitlines()
        if line.strip().startswith("uses:")
    ]
    assert uses_lines
    for line in uses_lines:
        target = line.split("uses:", 1)[1].strip().split(" #", 1)[0]
        assert re.search(r"@[0-9a-f]{40}$", target)


def test_schedule_does_not_run_more_than_daily() -> None:
    value = text()
    cron = re.search(r'cron:\s*"([^"]+)"', value)
    assert cron is not None
    fields = cron.group(1).split()
    assert len(fields) == 5
    assert fields[2:] == ["*", "*", "2"]


def test_workflow_never_uploads_registry_manifest_scratch_file() -> None:
    value = text()
    upload_block = value.split("Upload refresh proposal and provenance", 1)[1]
    assert "descriptor.json" not in upload_block
    assert "manifest.json" not in upload_block
    assert "container-queries.txt" not in upload_block
    assert "container-resolved.tsv" not in upload_block


def test_workflow_contract_has_one_mutating_checkout_phase_only() -> None:
    value = text()
    # The working tree is modified only by the reviewed apply phase; no shell
    # package manager or git mutation should precede it.
    before_apply = value.split("container_digest_refresh.py apply", 1)[0]
    assert "git checkout -b" not in before_apply
    assert "git reset" not in before_apply
    assert "git clean" not in before_apply
    assert "sed -i" not in before_apply
