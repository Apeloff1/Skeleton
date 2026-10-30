"""Reusable CI scopes its lanes; required readiness retains complete gates."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci_change_scope.sh"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init(repo: Path) -> None:
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "scope@example.com")
    _git(repo, "config", "user.name", "Scope Test")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "base")


def _scope(repo: Path, event: str) -> dict[str, str]:
    env = os.environ.copy()
    env["EVENT_NAME"] = event
    env.pop("GITHUB_OUTPUT", None)
    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=repo,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    return dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)


def test_non_pull_request_runs_every_lane(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init(repo)
    assert _scope(repo, "push") == {
        "frontend": "true",
        "backend": "true",
        "python": "true",
        "docker": "true",
    }


def test_pull_request_without_merge_parent_fails_closed_to_every_lane(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init(repo)
    assert _scope(repo, "pull_request")["python"] == "true"


def test_frontend_only_merge_skips_backend_python_and_docker(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init(repo)
    _git(repo, "checkout", "-b", "feature")
    frontend = repo / "frontend"
    frontend.mkdir()
    (frontend / "App.tsx").write_text("export {}\n", encoding="utf-8")
    _git(repo, "add", "frontend/App.tsx")
    _git(repo, "commit", "-m", "frontend")
    _git(repo, "checkout", "main")
    _git(repo, "merge", "--no-ff", "feature", "-m", "merge feature")
    assert _scope(repo, "pull_request") == {
        "frontend": "true",
        "backend": "false",
        "python": "false",
        "docker": "false",
    }


def test_ci_policy_edit_runs_every_lane(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init(repo)
    _git(repo, "checkout", "-b", "feature")
    workflow = repo / ".github" / "workflows"
    workflow.mkdir(parents=True)
    (workflow / "ci.yml").write_text("name: CI/CD\n", encoding="utf-8")
    _git(repo, "add", ".github/workflows/ci.yml")
    _git(repo, "commit", "-m", "ci")
    _git(repo, "checkout", "main")
    _git(repo, "merge", "--no-ff", "feature", "-m", "merge ci")
    assert set(_scope(repo, "pull_request").values()) == {"true"}


@pytest.mark.parametrize("changed_path", [
    "frontend/nginx.conf",
    "frontend/scripts/test-nginx-runtime-dns.mjs",
])
def test_frontend_ingress_changes_run_docker_regression(tmp_path: Path, changed_path: str) -> None:
    repo = tmp_path / "repo"
    _init(repo)
    _git(repo, "checkout", "-b", "feature")
    changed = repo / changed_path
    changed.parent.mkdir(parents=True)
    changed.write_text("ingress regression\n", encoding="utf-8")
    _git(repo, "add", changed_path)
    _git(repo, "commit", "-m", "ingress")
    _git(repo, "checkout", "main")
    _git(repo, "merge", "--no-ff", "feature", "-m", "merge ingress")
    assert _scope(repo, "pull_request") == {
        "frontend": "true",
        "backend": "false",
        "python": "false",
        "docker": "true",
    }


def test_large_pr_merge_does_not_drop_scoped_checks_on_broken_pipe(tmp_path: Path) -> None:
    """Over 4,000 changed paths must not turn true gates into false skips."""
    repo = tmp_path / "repo"
    _init(repo)
    _git(repo, "checkout", "-b", "feature")
    frontend = repo / "frontend" / "generated"
    frontend.mkdir(parents=True)
    for index in range(4_096):
        (frontend / f"long_generated_source_file_{index:05d}.tsx").write_text(
            "export const ready = true;\\n", encoding="utf-8"
        )
    backend = repo / "backend"
    backend.mkdir()
    (backend / "contract.py").write_text("READY = True\\n", encoding="utf-8")
    skeleton = repo / "skeleton"
    skeleton.mkdir()
    (skeleton / "contract.py").write_text("READY = True\\n", encoding="utf-8")
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", "large multi-plane change")
    _git(repo, "checkout", "main")
    _git(repo, "merge", "--no-ff", "feature", "-m", "merge large change")
    assert _scope(repo, "pull_request") == {
        "frontend": "true",
        "backend": "true",
        "python": "true",
        "docker": "false",
    }


def test_empty_merge_diff_fails_closed_to_every_lane(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init(repo)
    _git(repo, "checkout", "-b", "feature")
    (repo / "README.md").write_text("new intent\\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-m", "feature")
    _git(repo, "checkout", "main")
    _git(repo, "merge", "--no-ff", "-s", "ours", "feature", "-m", "empty-result merge")
    assert set(_scope(repo, "pull_request").values()) == {"true"}


def test_reusable_ci_calls_the_shared_scope_script_once() -> None:
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "bash scripts/ci_change_scope.sh" in ci
    assert ci.count("bash scripts/ci_change_scope.sh") == 1
    assert 'name: "Backend Lint"' in ci
    assert "yarn lint:ci" in ci


def test_required_readiness_keeps_complete_unit_and_security_gates() -> None:
    readiness = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "merge-readiness.yml").read_text(encoding="utf-8")
    )
    jobs = readiness["jobs"]
    unit_commands = [
        step for step in jobs["unit"]["steps"]
        if "python tests/run_unit.py" in step.get("run", "")
        or "skeleton/testing --tb=short" in " ".join(step.get("run", "").split())
    ]
    assert len(unit_commands) == 2
    assert all("if" not in step and not step.get("continue-on-error") for step in unit_commands)

    quality = jobs["quality_security"]
    security_commands = [
        step for step in quality["steps"]
        if "bash scripts/quality-gates.sh" in step.get("run", "")
    ]
    assert len(security_commands) == 1
    assert "if" not in security_commands[0]
    assert not security_commands[0].get("continue-on-error")
    for key in ("QUALITY_GATES_SKIP_FRONTEND", "QUALITY_GATES_SKIP_BACKEND_LINT"):
        assert key not in readiness.get("env", {})
        assert key not in quality.get("env", {})
        assert key not in security_commands[0].get("env", {})

    assert jobs["ci"]["uses"] == "./.github/workflows/ci.yml"
    assert "ci" in jobs["readiness"]["needs"]
