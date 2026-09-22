"""Shared fail-closed execution and publication helpers for repository bots."""
from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Mapping, Sequence

REPOSITORY = "Apeloff1/Skeleton"
REMOTE_URL = f"https://github.com/{REPOSITORY}.git"
_SENSITIVE_ENV_MARKERS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "API_KEY",
    "PRIVATE_KEY",
    "CREDENTIAL",
)
_SENSITIVE_ENV_EXACT = {
    "MODEL_API_URL",
    "MODEL_NAME",
    "ACTIONS_ID_TOKEN_REQUEST_URL",
    "GITHUB_WORKSPACE",
    "RUNNER_TEMP",
    "RUNNER_TOOL_CACHE",
}
_SAFE_PYTEST_PREFIXES = ("tests/", "skeleton/testing/")


def scrubbed_subprocess_env() -> dict[str, str]:
    """Return an environment safe for executing untrusted proposed code."""
    clean: dict[str, str] = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if key in _SENSITIVE_ENV_EXACT:
            continue
        if any(marker in upper for marker in _SENSITIVE_ENV_MARKERS):
            continue
        clean[key] = value
    return clean


def _safe_pytest_target(value: str) -> bool:
    if not value or value.startswith("-") or "\\" in value or "\x00" in value:
        return False
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        return False
    return value.startswith(_SAFE_PYTEST_PREFIXES)


def parse_test_command(command: str) -> list[str]:
    """Accept only fixed, non-shell test command shapes."""
    if not isinstance(command, str) or not command.strip():
        raise RuntimeError("invalid test command")
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise RuntimeError("invalid test command") from exc

    if argv in (
        ["python", "tests/run_unit.py"],
        ["python", "-m", "compileall", "-q", "skeleton"],
    ):
        return argv

    prefix = ["python", "-m", "pytest", "-q"]
    if argv[:4] == prefix:
        targets = argv[4:]
        if all(_safe_pytest_target(value) for value in targets):
            return argv

    raise RuntimeError("test command is outside the fixed allowlist")


def run_safe_tests(
    commands: object,
    *,
    require: bool,
    cwd: Path,
    max_commands: int = 3,
) -> None:
    if not isinstance(commands, list):
        if require:
            raise RuntimeError("source changes require explicit tests")
        return
    selected = commands[:max_commands]
    if require and not selected:
        raise RuntimeError("source changes require explicit tests")
    env = scrubbed_subprocess_env()
    for command in selected:
        argv = parse_test_command(command)
        subprocess.run(argv, check=True, timeout=300, env=env, cwd=cwd)


@contextmanager
def validation_workspace(files: Sequence[Mapping[str, str]]):
    """Validate proposals in a credential-free copy with no Git metadata."""
    with tempfile.TemporaryDirectory(prefix="skeleton-bot-validate-") as raw:
        root = Path(raw)
        archive = root / "repo.tar"
        work = root / "repo"
        work.mkdir()
        subprocess.run(
            ["git", "archive", "--format=tar", "HEAD", "-o", str(archive)],
            check=True,
            timeout=60,
            env=scrubbed_subprocess_env(),
        )
        subprocess.run(
            ["tar", "-xf", str(archive), "-C", str(work)],
            check=True,
            timeout=60,
            env=scrubbed_subprocess_env(),
        )
        write_plan_files(work, files)
        yield work


def safe_target(root: Path, repo_path: str) -> Path:
    """Resolve a proposed repo path without allowing symlink escape."""
    if not isinstance(repo_path, str) or not repo_path or "\\" in repo_path or "\x00" in repo_path:
        raise RuntimeError("unsafe repository path")
    relative = PurePosixPath(repo_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError("unsafe repository path")
    candidate = root.joinpath(*relative.parts)
    if candidate.is_symlink():
        raise RuntimeError("refusing to overwrite a symlink")
    resolved_root = root.resolve()
    resolved = candidate.resolve(strict=False)
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise RuntimeError("repository path escapes workspace")
    return candidate


def write_plan_files(root: Path, files: Sequence[Mapping[str, str]]) -> None:
    """Write bounded plan content without following final-component symlinks."""
    for item in files:
        path = item["path"]
        content = item["content"]
        target = safe_target(root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        flags |= getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(target, flags, 0o644)
        except OSError as exc:
            raise RuntimeError(f"failed safe write for {path}") from exc
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                fd = -1
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            if fd >= 0:
                os.close(fd)


def _git_env(token: str | None = None) -> dict[str, str]:
    env = scrubbed_subprocess_env()
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    if token:
        env["GH_TOKEN"] = token
    return env


def _git(
    args: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: int = 120,
) -> None:
    subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", *args],
        cwd=cwd,
        env=dict(env),
        check=True,
        timeout=timeout,
    )


def publish_pull_request(
    *,
    files: Sequence[Mapping[str, str]],
    token: str,
    base_sha: str,
    branch: str,
    title: str,
    body: str,
    commit_message: str,
) -> None:
    """Publish from a fresh temporary repository after validation has completed."""
    if not token:
        raise RuntimeError("GitHub token is required for publication")
    if len(base_sha) != 40 or any(ch not in "0123456789abcdef" for ch in base_sha):
        raise RuntimeError("invalid base commit")
    env = _git_env(token)

    with tempfile.TemporaryDirectory(prefix="skeleton-bot-publish-") as raw:
        repo_dir = Path(raw) / "repo"
        repo_dir.mkdir()
        _git(["init", "-q"], cwd=repo_dir, env=env)
        _git(["remote", "add", "origin", REMOTE_URL], cwd=repo_dir, env=env)
        _git(
            [
                "-c",
                "credential.helper=!gh auth git-credential",
                "fetch",
                "--depth=1",
                "origin",
                base_sha,
            ],
            cwd=repo_dir,
            env=env,
        )
        _git(["checkout", "-q", "-b", branch, "FETCH_HEAD"], cwd=repo_dir, env=env)
        write_plan_files(repo_dir, files)

        paths = [item["path"] for item in files]
        _git(["add", "--", *paths], cwd=repo_dir, env=env)
        diff = subprocess.run(
            ["git", "diff", "--cached", "--quiet", "--exit-code"],
            cwd=repo_dir,
            env=dict(env),
            timeout=30,
        )
        if diff.returncode == 0:
            raise RuntimeError("proposal has no effective changes")
        if diff.returncode not in (0, 1):
            raise RuntimeError("unable to inspect staged bot changes")

        _git(
            [
                "-c",
                "user.name=skeleton-repo-bot",
                "-c",
                "user.email=skeleton-repo-bot@users.noreply.github.com",
                "commit",
                "-q",
                "-m",
                commit_message,
            ],
            cwd=repo_dir,
            env=env,
        )
        _git(
            [
                "-c",
                "credential.helper=!gh auth git-credential",
                "push",
                REMOTE_URL,
                f"HEAD:refs/heads/{branch}",
            ],
            cwd=repo_dir,
            env=env,
        )
        subprocess.run(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                REPOSITORY,
                "--base",
                "main",
                "--head",
                branch,
                "--title",
                title,
                "--body",
                body[:8000],
            ],
            env=env,
            check=True,
            timeout=60,
        )
