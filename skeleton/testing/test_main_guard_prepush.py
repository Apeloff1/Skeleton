"""Hermetic tests for skeleton.main_guard.prepush (temp repos + bare remotes)."""

from __future__ import annotations

import io
import os
import subprocess
from pathlib import Path

import pytest

from skeleton.main_guard.gitops import Git
from skeleton.main_guard.prepush import (
    ZERO_SHA,
    RefUpdate,
    evaluate_updates,
    force_refspecs,
    hook_main,
    install_hook,
    map_tests,
    parse_hook_input,
    render_results,
    run_preflight,
)
from skeleton.testing.main_guard_test_support import clone, commit, git, git_env, init_repo, make_bare_remote

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def pair(tmp_path: Path) -> tuple[Path, Path, Path]:
    src = init_repo(tmp_path / "src")
    commit(src, {"pkg/mod.py": "X = 1\n", "skeleton/testing/test_mod.py": "def test_x():\n    assert True\n"}, "base")
    remote = make_bare_remote(tmp_path, src)
    other = clone(remote, tmp_path / "other")
    return src, remote, other


def _line(local_ref: str, local: str, remote_ref: str, remote: str) -> str:
    return f"{local_ref} {local} {remote_ref} {remote}\n"


def test_parse_hook_input_and_properties() -> None:
    ups = parse_hook_input([_line("refs/heads/main", "a" * 40, "refs/heads/main", ZERO_SHA), "\n"])
    assert len(ups) == 1 and ups[0].is_create and not ups[0].is_delete and ups[0].branch == "main"
    with pytest.raises(ValueError):
        parse_hook_input(["only three fields\n"])


@pytest.mark.parametrize("args,expected", [
    (["origin", "main"], []),
    (["origin", "+main"], ["+main"]),
    (["-f", "origin", "main"], ["-f"]),
    (["--force-with-lease=main", "origin"], ["--force-with-lease=main"]),
    (["--mirror"], ["--mirror"]),
])
def test_force_refspecs(args: list[str], expected: list[str]) -> None:
    assert force_refspecs(args) == expected


def test_fast_forward_is_allowed(pair: tuple[Path, Path, Path]) -> None:
    src, _remote, _other = pair
    old = git(src, "rev-parse", "HEAD")
    new = commit(src, {"pkg/mod.py": "X = 2\n"}, "ff")
    verdict = evaluate_updates(Git(src), [RefUpdate("refs/heads/main", new, "refs/heads/main", old)])
    assert verdict.ok, verdict.reasons


def test_non_fast_forward_is_refused(pair: tuple[Path, Path, Path]) -> None:
    src, _remote, _other = pair
    published = commit(src, {"pkg/mod.py": "X = 2\n"}, "published")
    git(src, "reset", "-q", "--hard", "HEAD~1")
    rewritten = commit(src, {"pkg/mod.py": "X = 3\n"}, "rewritten")
    verdict = evaluate_updates(Git(src), [RefUpdate("refs/heads/main", rewritten, "refs/heads/main", published)])
    assert not verdict.ok
    assert "non-fast-forward" in verdict.reasons[0]


def test_unknown_remote_tip_is_refused(pair: tuple[Path, Path, Path]) -> None:
    src, _remote, _other = pair
    head = git(src, "rev-parse", "HEAD")
    verdict = evaluate_updates(Git(src), [RefUpdate("refs/heads/main", head, "refs/heads/main", "f" * 40)])
    assert not verdict.ok and "pull --rebase" in verdict.reasons[0]


def test_protected_delete_refused_feature_delete_allowed(pair: tuple[Path, Path, Path]) -> None:
    src, _remote, _other = pair
    head = git(src, "rev-parse", "HEAD")
    bad = evaluate_updates(Git(src), [RefUpdate("(delete)", ZERO_SHA, "refs/heads/main", head)])
    good = evaluate_updates(Git(src), [RefUpdate("(delete)", ZERO_SHA, "refs/heads/feat/x", head)])
    assert not bad.ok and good.ok


def test_force_args_refused_even_if_fast_forward(pair: tuple[Path, Path, Path]) -> None:
    src, _remote, _other = pair
    old = git(src, "rev-parse", "HEAD")
    new = commit(src, {"pkg/mod.py": "X = 9\n"}, "ff")
    verdict = evaluate_updates(Git(src), [RefUpdate("refs/heads/main", new, "refs/heads/main", old)], push_args=["+main"])
    assert not verdict.ok


def test_hook_main_exit_codes(pair: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    src, _remote, _other = pair
    monkeypatch.delenv("MAIN_GUARD_PUSH_ARGS", raising=False)
    old = git(src, "rev-parse", "HEAD")
    new = commit(src, {"pkg/mod.py": "X = 4\n"}, "ff")
    err = io.StringIO()
    assert hook_main(["origin", "url"], io.StringIO(_line("refs/heads/main", new, "refs/heads/main", old)), err, repo=str(src)) == 0
    err = io.StringIO()
    assert hook_main([], io.StringIO(_line("refs/heads/main", old, "refs/heads/main", new)), err, repo=str(src)) == 1
    assert "push refused" in err.getvalue()
    assert hook_main([], io.StringIO("garbage\n"), io.StringIO(), repo=str(src)) == 2


def test_installed_hook_blocks_real_force_push(pair: tuple[Path, Path, Path]) -> None:
    src, _remote, other = pair
    git(other, "config", "core.hooksPath", str(other / ".git" / "hooks"))
    hook = install_hook(Git(other))
    assert hook.exists() and os.access(hook, os.X_OK)
    with pytest.raises(FileExistsError):
        (hook.parent / "pre-push").write_text("#!/bin/sh\nexit 0\n")
        install_hook(Git(other))
    install_hook(Git(other), overwrite=True)
    commit(src, {"pkg/mod.py": "X = 5\n"}, "upstream")
    git(src, "push", "-q", "origin", "main")
    commit(other, {"pkg/mod.py": "X = 6\n"}, "diverged")
    env = git_env(PYTHONPATH=str(REPO_ROOT))
    proc = subprocess.run(["git", "push", "--force", "origin", "main"], cwd=other, env=env, capture_output=True, text=True)
    assert proc.returncode != 0
    assert "non-fast-forward" in proc.stderr


def test_map_tests_picks_changed_and_related(tmp_path: Path) -> None:
    root = tmp_path
    for rel in ["skeleton/testing/test_main_guard_watcher.py", "skeleton/testing/test_widget.py",
                "backend/tests/test_queue_starvation.py", "skeleton/testing/test_unrelated.py"]:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("")
    picked = map_tests(["skeleton/main_guard/watcher.py", "skeleton/pr_automation/runner_hygiene/queue_starvation.py",
                        "skeleton/testing/test_widget.py", "README.md"], root)
    assert picked == ["backend/tests/test_queue_starvation.py", "skeleton/testing/test_main_guard_watcher.py",
                      "skeleton/testing/test_widget.py"]


def test_run_preflight_rebases_and_runs_mapped_tests(pair: tuple[Path, Path, Path]) -> None:
    src, _remote, other = pair
    commit(src, {"pkg/other.py": "Y = 1\n"}, "upstream moved")
    git(src, "push", "-q", "origin", "main")
    commit(other, {"pkg/mod.py": "X = 7\n"}, "local change")
    calls: list[list[str]] = []

    def runner(cmd, cwd):
        calls.append(list(cmd))
        if cmd[:2] == ["git", "pull"]:
            return subprocess.run(list(cmd), cwd=str(cwd), env=git_env(), capture_output=True, text=True)
        return subprocess.CompletedProcess(cmd, 0, "1 passed\n", "")

    results = run_preflight(other, runner=runner)
    assert all(r.ok for r in results), render_results(results)
    assert (other / "pkg/other.py").exists()
    pytest_calls = [c for c in calls if "pytest" in c]
    assert pytest_calls and "skeleton/testing/test_mod.py" in pytest_calls[0]
    assert "ready to push" in render_results(results)


def test_run_preflight_refuses_dirty_tree(pair: tuple[Path, Path, Path]) -> None:
    _src, _remote, other = pair
    (other / "pkg/mod.py").write_text("dirty\n")
    results = run_preflight(other)
    assert not results[-1].ok and "uncommitted" in results[-1].detail


def test_run_preflight_reports_failing_tests_and_missing_drift_script(pair: tuple[Path, Path, Path]) -> None:
    _src, _remote, other = pair
    commit(other, {"pkg/mod.py": "X = 8\n"}, "local")

    def runner(cmd, cwd):
        return subprocess.CompletedProcess(cmd, 1 if "pytest" in cmd else 0, "1 failed\n", "")

    results = run_preflight(other, pull=False, drift=True, runner=runner)
    by_name = {r.name: r for r in results}
    assert not by_name["tests"].ok
    assert by_name["ai file-tree drift"].ok and "skipped" in by_name["ai file-tree drift"].detail
    assert "NOT ready" in render_results(results)
