"""Pre-push guard for direct-to-main work on Skeleton.

Two entry points share this module:

* ``hook`` - installed as ``.git/hooks/pre-push``. Git feeds it one line per
  ref on stdin (``<local ref> <local sha> <remote ref> <remote sha>``). It
  refuses non-fast-forward updates (what ``--force`` produces), deletion of
  protected branches, and ``+`` force refspecs passed through
  ``MAIN_GUARD_PUSH_ARGS``.
* ``run`` - the manual pre-flight: ``git pull --rebase``, map the changed
  files to the test files that cover them, run those tests, and optionally the
  canonical AI file-tree drift check. Exit status is non-zero when anything
  fails so it can gate ``git push`` in scripts.

Assumption (noted per the no-confirmation rule): test mapping is heuristic.
It selects changed test files plus tests whose filename contains the changed
module's stem or its package name; ``--all-tests`` is the escape hatch.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from typing import Callable, Iterable, Sequence, TextIO

from skeleton.main_guard.gitops import Git, GitError

ZERO_SHA = "0" * 40
DEFAULT_PROTECTED = ("main", "master")
TEST_ROOTS = ("skeleton/testing", "backend/tests", "tests")
_TEST_NAME = re.compile(r"^test_.*\.py$|^.*_test\.py$")
DRIFT_SCRIPT = "scripts/check_ai_file_tree.py"


# --------------------------------------------------------------------------- hook


@dataclass(frozen=True)
class RefUpdate:
    local_ref: str
    local_sha: str
    remote_ref: str
    remote_sha: str

    @property
    def is_delete(self) -> bool:
        return self.local_sha == ZERO_SHA

    @property
    def is_create(self) -> bool:
        return self.remote_sha == ZERO_SHA

    @property
    def branch(self) -> str:
        prefix = "refs/heads/"
        return self.remote_ref[len(prefix):] if self.remote_ref.startswith(prefix) else self.remote_ref


@dataclass
class Verdict:
    ok: bool = True
    reasons: list[str] = field(default_factory=list)

    def refuse(self, reason: str) -> None:
        self.ok = False
        self.reasons.append(reason)


def parse_hook_input(stream: Iterable[str]) -> list[RefUpdate]:
    updates: list[RefUpdate] = []
    for raw in stream:
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 4:
            raise ValueError(f"malformed pre-push line: {line!r}")
        updates.append(RefUpdate(*parts))
    return updates


def force_refspecs(args: Sequence[str]) -> list[str]:
    """Return push arguments that request a forced update."""
    flagged = []
    for arg in args:
        if arg in {"-f", "--force", "--force-with-lease", "--force-if-includes"} or arg.startswith("--force-with-lease="):
            flagged.append(arg)
        elif arg.startswith("+") and len(arg) > 1:
            flagged.append(arg)
        elif arg.startswith("--mirror") or arg == "--prune":
            flagged.append(arg)
    return flagged


def evaluate_updates(
    git: Git,
    updates: Sequence[RefUpdate],
    *,
    protected: Sequence[str] = DEFAULT_PROTECTED,
    push_args: Sequence[str] = (),
    fetch_missing: Callable[[str], None] | None = None,
) -> Verdict:
    verdict = Verdict()
    for arg in force_refspecs(push_args):
        verdict.refuse(f"force push argument {arg!r} is not allowed")
    for upd in updates:
        if upd.is_delete:
            if upd.branch in protected:
                verdict.refuse(f"deleting protected branch {upd.branch!r} is not allowed")
            continue
        if upd.is_create:
            continue
        if not git.ok("cat-file", "-e", f"{upd.remote_sha}^{{commit}}") and fetch_missing is not None:
            fetch_missing(upd.remote_sha)
        if not git.ok("cat-file", "-e", f"{upd.remote_sha}^{{commit}}"):
            verdict.refuse(
                f"{upd.branch}: remote tip {upd.remote_sha[:12]} is not in your clone; "
                "run `git pull --rebase` first"
            )
            continue
        if not git.is_ancestor(upd.remote_sha, upd.local_sha):
            verdict.refuse(
                f"{upd.branch}: non-fast-forward update {upd.remote_sha[:12]} -> {upd.local_sha[:12]} "
                "rewrites published history (force push); rebase onto the remote instead"
            )
    return verdict


def hook_main(argv: Sequence[str], stdin: TextIO, stderr: TextIO, *, repo: str | None = None) -> int:
    parser = argparse.ArgumentParser(prog="main_guard prepush hook")
    parser.add_argument("remote_name", nargs="?", default="origin")
    parser.add_argument("remote_url", nargs="?", default="")
    parser.add_argument("--protected", action="append", default=None)
    ns = parser.parse_args(list(argv))
    git = Git(repo or os.getcwd())
    push_args = shlex.split(os.environ.get("MAIN_GUARD_PUSH_ARGS", ""))
    try:
        updates = parse_hook_input(stdin)
    except ValueError as exc:
        print(f"main-guard: {exc}", file=stderr)
        return 2

    def _fetch(sha: str) -> None:
        git.ok("fetch", "-q", ns.remote_name)

    verdict = evaluate_updates(git, updates, protected=tuple(ns.protected or DEFAULT_PROTECTED),
                               push_args=push_args, fetch_missing=_fetch)
    if verdict.ok:
        return 0
    print("main-guard: push refused", file=stderr)
    for reason in verdict.reasons:
        print(f"  - {reason}", file=stderr)
    print("  Fix: `git pull --rebase` then push again. Never force-push to shared branches.", file=stderr)
    return 1


HOOK_TEMPLATE = """#!/bin/sh
# Installed by skeleton.main_guard.prepush (refuses force pushes to protected branches).
exec "{python}" -m skeleton.main_guard.prepush hook "$@"
"""


def install_hook(git: Git, *, python: str = sys.executable, overwrite: bool = False) -> Path:
    hooks_dir = Path(git.out("rev-parse", "--git-path", "hooks"))
    if not hooks_dir.is_absolute():
        hooks_dir = git.toplevel() / hooks_dir
    hooks_dir.mkdir(parents=True, exist_ok=True)
    target = hooks_dir / "pre-push"
    if target.exists() and not overwrite and "skeleton.main_guard.prepush" not in target.read_text(errors="ignore"):
        raise FileExistsError(f"{target} exists and was not installed by main-guard (use --overwrite)")
    target.write_text(HOOK_TEMPLATE.format(python=python), encoding="utf-8")
    target.chmod(0o755)
    return target


# --------------------------------------------------------------------------- test mapping


def _all_test_files(root: Path, test_roots: Sequence[str]) -> list[str]:
    found: list[str] = []
    for rel in test_roots:
        base = root / rel
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if _TEST_NAME.match(path.name):
                found.append(path.relative_to(root).as_posix())
    return sorted(found)


def map_tests(changed: Iterable[str], root: Path, *, test_roots: Sequence[str] = TEST_ROOTS) -> list[str]:
    """Pick the test files most likely to cover ``changed`` paths."""
    candidates = _all_test_files(root, test_roots)
    picked: set[str] = set()
    for rel in changed:
        p = Path(rel)
        if p.suffix != ".py":
            continue
        if _TEST_NAME.match(p.name) and (root / rel).exists():
            picked.add(p.as_posix())
            continue
        stem = p.stem
        keys = {stem} if stem not in {"__init__", "__main__", "types", "utils", "cli"} else set()
        if len(p.parts) >= 2:
            pkg = p.parts[-2]
            if pkg not in {"skeleton", "ai", "backend", "scripts", "src"}:
                keys.add(pkg)
        for test in candidates:
            name = Path(test).stem
            if any(k and k in name for k in keys):
                picked.add(test)
    return sorted(picked)


# --------------------------------------------------------------------------- run


@dataclass
class StepResult:
    name: str
    ok: bool
    detail: str = ""


Runner = Callable[[Sequence[str], Path], "subprocess.CompletedProcess[str]"]


def _default_runner(cmd: Sequence[str], cwd: Path) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(list(cmd), cwd=str(cwd), capture_output=True, text=True, check=False)


def run_preflight(
    repo: str | os.PathLike[str],
    *,
    remote: str = "origin",
    branch: str = "main",
    pull: bool = True,
    tests: bool = True,
    all_tests: bool = False,
    drift: bool = False,
    extra_tests: Sequence[str] = (),
    runner: Runner = _default_runner,
    log: Callable[[str], None] = lambda _m: None,
) -> list[StepResult]:
    git = Git(repo)
    root = git.toplevel()
    results: list[StepResult] = []

    if pull:
        if git.is_dirty():
            results.append(StepResult("pull --rebase", False, "working tree has uncommitted changes; commit or stash first"))
            return results
        log(f"git pull --rebase {remote} {branch}")
        proc = runner(["git", "pull", "--rebase", remote, branch], root)
        if proc.returncode != 0:
            runner(["git", "rebase", "--abort"], root)
            results.append(StepResult("pull --rebase", False, (proc.stderr or proc.stdout).strip()[-2000:]))
            return results
        results.append(StepResult("pull --rebase", True))

    upstream = f"{remote}/{branch}"
    base = git.try_rev_parse(upstream)
    changed: list[str] = []
    if base is not None:
        mb = git.merge_base(base, "HEAD") or base
        changed = git.changed_files(mb, "HEAD")
    results.append(StepResult("changed files", True, ", ".join(changed[:50]) + (" ..." if len(changed) > 50 else "")))

    if tests:
        selected = list(extra_tests)
        if all_tests:
            selected = [r for r in TEST_ROOTS if (root / r).is_dir()]
        else:
            selected += [t for t in map_tests(changed, root) if t not in selected]
        if not selected:
            results.append(StepResult("tests", True, "no mapped tests for the changed files"))
        else:
            log("pytest " + " ".join(selected))
            proc = runner([sys.executable, "-m", "pytest", "-q", *selected], root)
            tail = (proc.stdout or proc.stderr).strip().splitlines()[-3:]
            results.append(StepResult("tests", proc.returncode == 0, " | ".join(tail)))

    if drift:
        script = root / DRIFT_SCRIPT
        if not script.exists():
            results.append(StepResult("ai file-tree drift", True, f"{DRIFT_SCRIPT} not present; skipped"))
        else:
            proc = runner([sys.executable, str(script)], root)
            results.append(StepResult("ai file-tree drift", proc.returncode == 0, (proc.stdout + proc.stderr).strip()[-2000:]))
    return results


def render_results(results: Sequence[StepResult]) -> str:
    lines = []
    for r in results:
        mark = "PASS" if r.ok else "FAIL"
        lines.append(f"[{mark}] {r.name}" + (f": {r.detail}" if r.detail else ""))
    ok = all(r.ok for r in results)
    lines.append("main-guard: ready to push" if ok else "main-guard: NOT ready to push")
    return "\n".join(lines)


# --------------------------------------------------------------------------- cli


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "hook":
        return hook_main(args[1:], sys.stdin, sys.stderr)
    parser = argparse.ArgumentParser(prog="python -m skeleton.main_guard.prepush")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="pull --rebase, run mapped tests, optional drift check")
    run.add_argument("--repo", default=".")
    run.add_argument("--remote", default="origin")
    run.add_argument("--branch", default="main")
    run.add_argument("--no-pull", action="store_true")
    run.add_argument("--no-tests", action="store_true")
    run.add_argument("--all-tests", action="store_true")
    run.add_argument("--drift", action="store_true")
    run.add_argument("--test", action="append", default=[])
    inst = sub.add_parser("install", help="install the pre-push hook into this clone")
    inst.add_argument("--repo", default=".")
    inst.add_argument("--overwrite", action="store_true")
    ns = parser.parse_args(args)
    if ns.cmd == "install":
        try:
            path = install_hook(Git(ns.repo), overwrite=ns.overwrite)
        except (FileExistsError, GitError) as exc:
            print(f"main-guard: {exc}", file=sys.stderr)
            return 1
        print(f"main-guard: installed {path}")
        return 0
    results = run_preflight(ns.repo, remote=ns.remote, branch=ns.branch, pull=not ns.no_pull,
                            tests=not ns.no_tests, all_tests=ns.all_tests, drift=ns.drift,
                            extra_tests=ns.test, log=lambda m: print(f"main-guard: {m}", file=sys.stderr))
    print(render_results(results))
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
