"""Physical Docker CI qualification source contract (no host daemon needed)."""
from __future__ import annotations

import os
from pathlib import Path
from unittest import mock
import subprocess

import pytest

from scripts import qualify_local_ai_cold_backup_docker as acceptance
from scripts import local_ai_docker as host


def test_real_daemon_acceptance_denies_non_ci_hosts(monkeypatch, tmp_path):
    for value in (None, "false", ""):
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.setenv("CI", "true")
        monkeypatch.setenv("GITHUB_REPOSITORY", "Apeloff1/Skeleton")
        if value is not None:
            monkeypatch.setenv("GITHUB_ACTIONS", value)
        with mock.patch.object(acceptance, "_safe_call") as command:
            with pytest.raises(acceptance.EphemeralDockerAcceptanceError):
                acceptance.qualify_ephemeral_cold_copy(tmp_path)
            command.assert_not_called()


def test_untrusted_github_repos_cannot_create_or_delete_real_docker_volumes(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("CI", "true")
    for other in ("other/fork", "apeloff1/skeleton", "Apeloff1/Skeleton-archive"):
        monkeypatch.setenv("GITHUB_REPOSITORY", other)
        with mock.patch.object(acceptance, "_safe_call") as command:
            with pytest.raises(acceptance.EphemeralDockerAcceptanceError):
                acceptance.qualify_ephemeral_cold_copy(tmp_path)
            command.assert_not_called()


def test_worker_image_build_inherits_canonical_digest_pinned_python(tmp_path):
    canonical = tmp_path / "Dockerfile"
    canonical.write_text(
        "ARG PYTHON_IMAGE=python:3.14-slim@sha256:" + "a" * 64 + "\n"
        "FROM ${PYTHON_IMAGE}\n"
    )
    assert acceptance._image_base(tmp_path) == (
        "python:3.14-slim@sha256:" + "a" * 64
    )
    canonical.write_text("FROM python:latest\n")
    with pytest.raises(acceptance.EphemeralDockerAcceptanceError):
        acceptance._image_base(tmp_path)


@pytest.mark.parametrize("command", [
    ["docker", "volume", "inspect", "missing"],
    ["docker", "run", "--help"],
])
def test_expected_docker_failures_never_promote_a_success(command):
    with mock.patch.object(
        acceptance.subprocess, "run",
        return_value=subprocess.CompletedProcess(command, 0, stdout=""),
    ):
        with pytest.raises(acceptance.EphemeralDockerAcceptanceError):
            acceptance._fail_command(command)


def test_nonzero_docker_exit_does_not_echo_private_stderr():
    with mock.patch.object(
        acceptance.subprocess, "run",
        return_value=subprocess.CompletedProcess(
            ["docker"], 1, stdout="", stderr="private credential and document"
        ),
    ):
        with pytest.raises(acceptance.EphemeralDockerAcceptanceError) as ex:
            acceptance._safe_call(["docker", "info"])
    assert "private" not in str(ex.value)
    assert "credential" not in str(ex.value)


def test_source_ci_workflow_is_review_only_and_exact_head():
    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/backend-quality.yml").read_text()
    script = (root / "scripts/qualify_local_ai_cold_backup_docker.py").read_text()
    assert "docker_ephemeral_cold_archive:" in workflow
    assert "startsWith(github.head_ref, 'feat/docker-local-ai-runtime-')" in workflow
    assert "github.event.pull_request.head.repo.full_name == github.repository" in workflow
    assert "persist-credentials: false" in workflow
    assert "ref: ${{ github.event.pull_request.head.sha }}" in workflow
    assert "python scripts/qualify_local_ai_cold_backup_docker.py" in workflow
    assert "GITHUB_ACTIONS" in script
    assert "GITHUB_REPOSITORY" in script
    assert '"docker", "volume", "rm", volume' in script
    assert '"docker", "image", "rm", worker_name' in script
    assert "missing_source_created" in script
    assert "mongo_database_consistency_qualified" in script
    assert "application_restore_qualified" in script
    assert "guarded_jeeves_qualified" in script


def test_ci_synthetic_seed_is_offline_and_is_not_real_user_data():
    source = Path(acceptance.__file__).read_text(encoding="utf-8")
    assert "--network=none" in source
    assert "SYNTHETIC-COLD" in source
    assert "private" not in acceptance._SCHEMA
    assert "real_application_volume_accessed" in source


def test_worker_build_uses_only_pinned_base_and_canonical_script(tmp_path):
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "scripts/local_ai_volume_copy.py").write_text("print('synthetic test')\n")
    (root / "Dockerfile").write_text(
        "ARG PYTHON_IMAGE=python:3.14-slim@sha256:" + "b" * 64 + "\n"
    )
    context = tmp_path / "context"
    image = "ci-worker-test:v1"
    with mock.patch.object(acceptance, "_safe_call", side_effect=[
        "sha256:" + "b" * 64, "sha256:" + "b" * 64,
    ]) as run:
        assert acceptance._build_worker(context, image, root) == "sha256:" + "b" * 64
    written = (context / "Dockerfile").read_text()
    assert written.startswith("FROM python:3.14-slim@sha256:" + "b" * 64)
    assert "COPY scripts /app/scripts" in written
    assert "COPY . ." not in written
    assert (context / "scripts/local_ai_volume_copy.py").read_text() == (
        "print('synthetic test')\n"
    )
    assert run.call_count == 2


@pytest.mark.parametrize("reason", [
    "worker-copy-rejected", "worker-copy-io",
    "worker-copy-source-mutated", "worker-copy-ok",
])
def test_disposable_copy_diagnostic_preserves_strict_docker_isolation(
    reason, tmp_path,
):
    with mock.patch.object(acceptance, "_safe_call", return_value=reason) as run:
        result = acceptance._probe_failed_worker_copy(
            "sha256:" + "a" * 64,
            "/var/lib/docker/volumes/ci-synthetic-mongo_data/_data",
            tmp_path,
        )
    assert result == reason
    args = run.call_args.args[0]
    assert "--network=none" in args
    assert "--read-only" in args
    assert "--cap-drop=ALL" in args
    assert "--security-opt=no-new-privileges" in args
    assert any("no-new-privileges" in item for item in args)
    assert "--user=0:0" in args
    assert any(part.endswith(",target=/source,readonly") for part in args)
    assert any(part.endswith(",target=/archive") for part in args)
    assert "try:\\n" not in args[-1]
    assert "try:\n" in args[-1]
    assert run.call_args.kwargs["stage_override"] == "worker-copy"


def test_disposable_diagnostic_never_publishes_unknown_worker_output(tmp_path):
    private = "private credential and /home/user/archive"
    with mock.patch.object(acceptance, "_safe_call", return_value=private):
        result = acceptance._probe_failed_worker_copy(
            "sha256:" + "b" * 64, "/var/lib/docker/volumes/synthetic/_data",
            tmp_path,
        )
    assert result == "worker-copy-probe-unavailable"
    assert private not in result


def test_disposable_diagnostic_fails_closed_on_container_failure(tmp_path):
    with mock.patch.object(
        acceptance, "_safe_call",
        side_effect=acceptance.EphemeralDockerAcceptanceError("worker-copy"),
    ):
        assert acceptance._probe_failed_worker_copy(
            "sha256:" + "c" * 64, "/var/lib/docker/volumes/synthetic/_data",
            tmp_path,
        ) == "worker-copy-probe-unavailable"

@pytest.mark.parametrize("result", [
    "worker-copy-source-access", "worker-copy-archive-access",
])
def test_disposable_access_probe_reports_only_fixed_denial_codes(result, tmp_path):
    with mock.patch.object(acceptance, "_safe_call", return_value=result) as run:
        observed = acceptance._probe_failed_worker_copy(
            "sha256:" + "a" * 64,
            "/var/lib/docker/volumes/ci-synthetic-mongo_data/_data",
            tmp_path,
        )
    assert observed == result
    command = run.call_args.args[0]
    assert "--network=none" in command
    assert "--cap-drop=ALL" in command
    assert "--user=0:0" in command
    assert any(x.endswith(",target=/source,readonly") for x in command)
    assert any(x.endswith(",target=/archive") for x in command)
    assert "private" not in observed
