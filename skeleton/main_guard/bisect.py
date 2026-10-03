"""Find the first bad commit when several pushes landed between CI runs.

Two strategies are provided:

``git``
    Wraps ``git bisect start``/``git bisect run`` in the caller's checkout.
    Requires a clean tracked working tree.  The original branch/HEAD and bisect
    state are *always* restored in a ``finally`` block, and restoration is
    verified afterwards.

``direct`` (default)
    Implements the binary search itself inside a throw-away detached
    ``git worktree``.  The caller's checkout, index, HEAD and bisect state are
    never touched, so it is safe to run while other work is in progress.  Uses
    the first-parent chain by default, which is exact for direct-to-main
    history.

Both strategies share git-bisect exit-code semantics for the test command:
``0`` good, ``125`` skip, ``1..127`` (except 125) bad, anything else aborts.
A per-step timeout is mapped to *skip* by default (``timeout_as="skip"``) or to
*bad* when requested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Callable, Mapping, Sequence

from .gitops import CommitInfo, Git, GitError

GOOD = "good"
BAD = "bad"
SKIP = "skip"
SKIP_CODE = 125
ABORT_THRESHOLD = 128

_FIRST_BAD = re.compile(r"^([0-9a-f]{40}) is the first bad commit", re.MULTILINE)
_COULD_BE = re.compile(r"first bad commit could be any of:\s*\n((?:[0-9a-f]{40}\s*\n?)+)", re.MULTILINE)


class BisectError(RuntimeError):
    """The bisect could not be started, run, or cleanly restored."""


@dataclass(frozen=True, slots=True)
class BisectStep:
    sha: str
    outcome: str
    returncode: int | None
    duration_s: float
    timed_out: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "sha": self.sha,
            "outcome": self.outcome,
            "returncode": self.returncode,
            "duration_s": round(self.duration_s, 3),
            "timed_out": self.timed_out,
        }


@dataclass(slots=True)
class BisectResult:
    strategy: str
    good: str
    bad: str
    command: list[str]
    first_bad: CommitInfo | None = None
    candidates: list[CommitInfo] = field(default_factory=list)
    steps: list[BisectStep] = field(default_factory=list)
    range_size: int = 0
    restored_head: str | None = None
    restored_branch: str | None = None

    @property
    def found(self) -> bool:
        return self.first_bad is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy": self.strategy,
            "good": self.good,
            "bad": self.bad,
            "command": list(self.command),
            "found": self.found,
            "first_bad": self.first_bad.to_dict() if self.first_bad else None,
            "candidates": [c.to_dict() for c in self.candidates],
            "steps": [s.to_dict() for s in self.steps],
            "range_size": self.range_size,
            "restored_head": self.restored_head,
            "restored_branch": self.restored_branch,
        }


def classify_returncode(code: int | None, *, timed_out: bool = False, timeout_as: str = SKIP) -> str:
    """Map a process exit to good/bad/skip using git-bisect semantics."""
    if timed_out:
        return BAD if timeout_as == BAD else SKIP
    if code is None:
        raise BisectError("test command produced no exit status")
    if code == 0:
        return GOOD
    if code == SKIP_CODE:
        return SKIP
    if 0 < code < ABORT_THRESHOLD:
        return BAD
    raise BisectError(f"test command exited with {code}; aborting bisect (exit >= 128 or signal)")


StepRunner = Callable[[Path, str], BisectStep]


def make_step_runner(
    command: Sequence[str],
    *,
    timeout_s: float | None = None,
    timeout_as: str = SKIP,
    env: Mapping[str, str] | None = None,
    log: Callable[[str], None] | None = None,
) -> StepRunner:
    """Build a runner executing ``command`` in a checkout directory."""
    argv = list(command)
    if not argv:
        raise BisectError("a test command is required")

    def run(cwd: Path, sha: str) -> BisectStep:
        merged = dict(os.environ)
        if env:
            merged.update(env)
        merged["MAIN_GUARD_BISECT_SHA"] = sha
        started = time.monotonic()
        timed_out = False
        code: int | None
        try:
            proc = subprocess.run(argv, cwd=str(cwd), env=merged, capture_output=True, text=True,
                                  timeout=timeout_s, check=False)
            code = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            code = None
        except FileNotFoundError as exc:
            raise BisectError(f"test command not found: {exc}") from exc
        if code is not None and code < 0:
            raise BisectError(f"test command killed by signal {-code}; aborting bisect")
        outcome = classify_returncode(code, timed_out=timed_out, timeout_as=timeout_as)
        step = BisectStep(sha=sha, outcome=outcome, returncode=code,
                          duration_s=time.monotonic() - started, timed_out=timed_out)
        if log:
            log(f"bisect: {sha[:10]} -> {outcome}" + (" (timeout)" if timed_out else f" (exit {code})"))
        return step

    return run


def candidate_range(git: Git, good: str, bad: str, *, first_parent: bool = True) -> list[str]:
    """Commits after ``good`` up to and including ``bad``, oldest first."""
    if good == bad:
        raise BisectError("good and bad revisions are the same commit")
    if not git.is_ancestor(good, bad):
        raise BisectError(f"good {good[:10]} is not an ancestor of bad {bad[:10]}")
    revs = git.rev_list([f"{good}..{bad}"], first_parent=first_parent, reverse=True,
                        ancestry_path=not first_parent)
    if not revs or revs[-1] != bad:
        raise BisectError("could not build a linear candidate range ending at the bad commit")
    return revs


def binary_search(
    candidates: Sequence[str],
    probe: Callable[[str], str],
) -> tuple[int | None, list[int], list[tuple[int, str]]]:
    """Search for the first bad index in ``candidates`` (last element is bad).

    ``probe`` returns good/bad/skip for a commit.  Returns
    ``(first_bad_index, ambiguous_indices, probes)``; when skips make the
    answer ambiguous ``first_bad_index`` is ``None`` and ``ambiguous_indices``
    lists every index that could be the first bad commit.
    """
    lo, hi = -1, len(candidates) - 1
    skipped: set[int] = set()
    probes: list[tuple[int, str]] = []
    while hi - lo > 1:
        open_ = [i for i in range(lo + 1, hi) if i not in skipped]
        if not open_:
            ambiguous = [i for i in range(lo + 1, hi + 1)]
            return None, ambiguous, probes
        target = (lo + hi) / 2
        mid = min(open_, key=lambda i: (abs(i - target), i))
        outcome = probe(candidates[mid])
        probes.append((mid, outcome))
        if outcome == GOOD:
            lo = mid
        elif outcome == BAD:
            hi = mid
        elif outcome == SKIP:
            skipped.add(mid)
        else:  # pragma: no cover - defensive
            raise BisectError(f"unknown probe outcome {outcome!r}")
    return hi, [], probes


def _bisect_in_progress(git: Git) -> bool:
    return (git.git_dir() / "BISECT_START").exists()


class DirectBisect:
    """Binary search in a disposable detached worktree."""

    def __init__(self, git: Git, runner: StepRunner, *, first_parent: bool = True,
                 verify_endpoints: bool = True, log: Callable[[str], None] | None = None) -> None:
        self.git = git
        self.runner = runner
        self.first_parent = first_parent
        self.verify_endpoints = verify_endpoints
        self.log = log or (lambda _msg: None)

    def run(self, good: str, bad: str, command: Sequence[str]) -> BisectResult:
        good_sha = self.git.rev_parse(good)
        bad_sha = self.git.rev_parse(bad)
        candidates = candidate_range(self.git, good_sha, bad_sha, first_parent=self.first_parent)
        result = BisectResult(strategy="direct", good=good_sha, bad=bad_sha, command=list(command),
                              range_size=len(candidates))
        head_before = self.git.head_sha()
        branch_before = self.git.current_branch()
        tmp = Path(tempfile.mkdtemp(prefix="main-guard-bisect-"))
        worktree = tmp / "wt"
        added = False
        try:
            self.git.run("worktree", "add", "--detach", "--force", str(worktree), bad_sha)
            added = True
            wt_git = Git(worktree, timeout_s=self.git.timeout_s)

            def probe(sha: str) -> str:
                wt_git.run("checkout", "--detach", "--force", "--quiet", sha)
                wt_git.run("clean", "-fdq")
                step = self.runner(worktree, sha)
                result.steps.append(step)
                return step.outcome

            if self.verify_endpoints:
                if probe(good_sha) != GOOD:
                    raise BisectError(f"test command does not pass at good {good_sha[:10]}")
                if probe(bad_sha) != BAD:
                    raise BisectError(f"test command does not fail at bad {bad_sha[:10]}")
            index, ambiguous, _ = binary_search(candidates, probe)
            if index is not None:
                result.first_bad = self.git.commit(candidates[index])
            else:
                result.candidates = self.git.commits([candidates[i] for i in ambiguous])
        finally:
            if added:
                self.git.run("worktree", "remove", "--force", str(worktree), check=False)
            self.git.run("worktree", "prune", check=False)
            _rmtree_quiet(tmp)
        result.restored_head = self.git.head_sha()
        result.restored_branch = self.git.current_branch()
        if result.restored_head != head_before or result.restored_branch != branch_before:
            raise BisectError("caller checkout changed during direct bisect")  # pragma: no cover
        return result


_WRAPPER_SOURCE = r'''
import json, subprocess, sys, time
log_path, timeout_raw, timeout_as = sys.argv[1], sys.argv[2], sys.argv[3]
argv = sys.argv[4:]
sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
started = time.monotonic()
timeout = float(timeout_raw) if timeout_raw != "none" else None
timed_out = False
try:
    code = subprocess.run(argv, timeout=timeout).returncode
except subprocess.TimeoutExpired:
    timed_out = True
    code = None
except FileNotFoundError:
    code = 127
if timed_out:
    exit_code = 1 if timeout_as == "bad" else 125
elif code is None or code < 0:
    exit_code = 255
else:
    exit_code = code
with open(log_path, "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"sha": sha, "returncode": code, "timed_out": timed_out,
                         "duration_s": time.monotonic() - started, "exit": exit_code}) + "\n")
sys.exit(exit_code)
'''


class GitBisectRun:
    """Wrap ``git bisect run`` and always restore the caller's HEAD."""

    def __init__(self, git: Git, *, first_parent: bool = False, timeout_s: float | None = None,
                 timeout_as: str = SKIP, total_timeout_s: float = 3600.0,
                 log: Callable[[str], None] | None = None) -> None:
        self.git = git
        self.first_parent = first_parent
        self.timeout_s = timeout_s
        self.timeout_as = timeout_as
        self.total_timeout_s = total_timeout_s
        self.log = log or (lambda _msg: None)

    def run(self, good: str, bad: str, command: Sequence[str]) -> BisectResult:
        if not command:
            raise BisectError("a test command is required")
        if _bisect_in_progress(self.git):
            raise BisectError("a git bisect is already in progress; run `git bisect reset` first")
        if self.git.is_dirty():
            raise BisectError("working tree has tracked changes; commit/stash them or use --strategy direct")
        good_sha = self.git.rev_parse(good)
        bad_sha = self.git.rev_parse(bad)
        candidates = candidate_range(self.git, good_sha, bad_sha, first_parent=self.first_parent)
        result = BisectResult(strategy="git", good=good_sha, bad=bad_sha, command=list(command),
                              range_size=len(candidates))
        head_before = self.git.head_sha()
        branch_before = self.git.current_branch()
        tmp = Path(tempfile.mkdtemp(prefix="main-guard-gitbisect-"))
        wrapper = tmp / "step.py"
        steps_log = tmp / "steps.jsonl"
        wrapper.write_text(_WRAPPER_SOURCE, encoding="utf-8")
        output = ""
        try:
            start = ["bisect", "start"]
            if self.first_parent:
                start.append("--first-parent")
            start.extend([bad_sha, good_sha])
            self.git.run(*start)
            proc = self.git.run(
                "bisect", "run", sys.executable, str(wrapper), str(steps_log),
                "none" if self.timeout_s is None else str(self.timeout_s), self.timeout_as, *command,
                check=False, timeout_s=self.total_timeout_s,
            )
            output = f"{proc.stdout}\n{proc.stderr}"
            result.steps = _read_steps(steps_log)
            match = _FIRST_BAD.search(output)
            if match:
                result.first_bad = self.git.commit(match.group(1))
            else:
                could = _COULD_BE.search(output)
                if could:
                    shas = [s for s in could.group(1).split() if s]
                    result.candidates = self.git.commits(shas)
                elif proc.returncode != 0:
                    raise BisectError("git bisect run failed: " + (output.strip().splitlines() or ["?"])[-1])
        finally:
            self._restore(head_before, branch_before)
            _rmtree_quiet(tmp)
        result.restored_head = self.git.head_sha()
        result.restored_branch = self.git.current_branch()
        return result

    def _restore(self, head_before: str, branch_before: str | None) -> None:
        target = branch_before or head_before
        reset = self.git.run("bisect", "reset", target, check=False)
        if reset.returncode != 0 or _bisect_in_progress(self.git):
            self.git.run("bisect", "reset", check=False)
            if branch_before:
                self.git.run("checkout", "--quiet", branch_before, check=False)
            else:
                self.git.run("checkout", "--quiet", "--detach", head_before, check=False)
        if _bisect_in_progress(self.git):
            raise BisectError("failed to clear bisect state; run `git bisect reset` manually")
        if self.git.head_sha() != head_before or self.git.current_branch() != branch_before:
            raise BisectError(
                f"failed to restore original HEAD {head_before[:10]} ({branch_before or 'detached'})"
            )


def _read_steps(path: Path) -> list[BisectStep]:
    steps: list[BisectStep] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return steps
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        code = row.get("exit")
        outcome = GOOD if code == 0 else SKIP if code == SKIP_CODE else BAD if isinstance(code, int) and 0 < code < 128 else "abort"
        steps.append(BisectStep(sha=str(row.get("sha", "")), outcome=outcome,
                                returncode=row.get("returncode"),
                                duration_s=float(row.get("duration_s") or 0.0),
                                timed_out=bool(row.get("timed_out"))))
    return steps


def _rmtree_quiet(path: Path) -> None:
    import shutil

    shutil.rmtree(path, ignore_errors=True)


def bisect(
    repo: str | os.PathLike[str],
    good: str,
    bad: str,
    command: Sequence[str],
    *,
    strategy: str = "direct",
    first_parent: bool = True,
    timeout_s: float | None = None,
    timeout_as: str = SKIP,
    verify_endpoints: bool = True,
    log: Callable[[str], None] | None = None,
) -> BisectResult:
    """Convenience entry point used by the CLI."""
    git = Git(repo)
    try:
        git.toplevel()
    except GitError as exc:
        raise BisectError(f"not a git repository: {repo}") from exc
    if strategy == "direct":
        runner = make_step_runner(command, timeout_s=timeout_s, timeout_as=timeout_as, log=log)
        return DirectBisect(git, runner, first_parent=first_parent, verify_endpoints=verify_endpoints,
                            log=log).run(good, bad, command)
    if strategy == "git":
        return GitBisectRun(git, first_parent=first_parent, timeout_s=timeout_s, timeout_as=timeout_as,
                            log=log).run(good, bad, command)
    raise BisectError(f"unknown strategy {strategy!r} (expected 'direct' or 'git')")


def render_bisect_markdown(result: BisectResult) -> str:
    from .notice import author_label, commit_line, md_escape

    cmd = " ".join(result.command)
    lines = [
        "### main-guard bisect",
        "",
        f"- Range: `{result.good[:10]}` (good) .. `{result.bad[:10]}` (bad), {result.range_size} candidate(s)",
        f"- Strategy: `{result.strategy}`; command: `{md_escape(cmd)}`",
        f"- Steps run: {len(result.steps)}",
    ]
    if result.first_bad:
        lines += [
            "",
            f"**First bad commit:** {commit_line(result.first_bad)}",
            "",
            f"Fix-forward owner: {author_label(result.first_bad)} — please push a fix to `main` "
            f"that makes `{md_escape(cmd)}` pass again.",
        ]
    elif result.candidates:
        lines += ["", "**Ambiguous (skipped commits):** the first bad commit is one of:"]
        lines += [f"- {commit_line(c)}" for c in result.candidates]
    else:
        lines += ["", "No first bad commit identified."]
    lines += ["", f"Restored HEAD: `{(result.restored_head or '')[:10]}` "
                  f"({result.restored_branch or 'detached'})"]
    return "\n".join(lines) + "\n"
