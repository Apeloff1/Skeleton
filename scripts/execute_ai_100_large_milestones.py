#!/usr/bin/env python3
"""Execute the original 100 MDM milestones against canonical implementation tests.

This is a real, opt-in host test runner, not a completion-signoff generator.
It verifies canonical plan/source pins, resolves each milestone's actual tests,
executes them with bounded local resources, and writes hash-linked evidence.
A passing run means only *these* checks passed on the pinned source snapshot.
Independent review, feature completeness and rollback proof remain separate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable, Mapping, Sequence

try:
    from scripts.check_ai_100_large_milestones import FILES, ROOT, load_json, verify
except ModuleNotFoundError:
    from check_ai_100_large_milestones import FILES, ROOT, load_json, verify

SCHEMA = "skeleton.ai.real_milestone_execution.v1"
_SHA = re.compile(r"^[0-9a-f]{40}$")
_MILESTONE = re.compile(r"^MDM-(?:00[1-9]|0[1-9][0-9]|100)$")
_PATH = re.compile(r"^[A-Za-z0-9_./-]{1,240}$")
_ALLOWED_TEST_ROOTS = ("tests/", "skeleton/testing/", "backend/tests/")
_ALLOWED_SCRIPT_ROOTS = ("scripts/check_",)
_MAX_TESTS = 1000
_MAX_TEST_SECONDS = 900
_MAX_CAPTURE_BYTES = 32 * 1024 * 1024


class MilestoneExecutionError(ValueError):
    """The requested execution would be unsafe or its evidence is incomplete."""


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _safe_test(path: str, root: Path) -> tuple[str, Path]:
    if not isinstance(path, str) or not _PATH.fullmatch(path):
        raise MilestoneExecutionError("invalid test path")
    parsed = PurePosixPath(path)
    if (".." in parsed.parts or str(parsed) != path or path.startswith("/")
            or "//" in path or "/./" in path):
        raise MilestoneExecutionError("noncanonical test path")
    if path.startswith(_ALLOWED_TEST_ROOTS) and path.endswith(".py"):
        kind = "pytest"
    elif path.startswith(_ALLOWED_SCRIPT_ROOTS) and path.endswith(".py"):
        kind = "policy"
    else:
        raise MilestoneExecutionError("milestone test outside approved execution roots")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise MilestoneExecutionError("missing or escaping milestone test: " + path)
    return kind, resolved


def _safe_selection(requested: Sequence[str]) -> tuple[str, ...]:
    result = tuple(dict.fromkeys(requested))
    if not result or len(result) > 100:
        raise MilestoneExecutionError("must choose between one and 100 milestones")
    if any(not isinstance(item, str) or not _MILESTONE.fullmatch(item) for item in result):
        raise MilestoneExecutionError("invalid canonical MDM milestone identity")
    return result


@dataclass(frozen=True, slots=True)
class PlannedCheck:
    path: str
    kind: str
    volumes: tuple[str, ...]
    milestones: tuple[str, ...]
    source_digest: str

    @property
    def fingerprint(self) -> str:
        return _hash(_canonical_json({
            "path": self.path, "kind": self.kind,
            "volumes": self.volumes, "milestones": self.milestones,
            "source_digest": self.source_digest,
        }))


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    source_commit: str
    requested: tuple[str, ...]
    canonical_roadmap_sha: str
    checks: tuple[PlannedCheck, ...]

    @property
    def fingerprint(self) -> str:
        return _hash(_canonical_json({
            "commit": self.source_commit,
            "milestones": self.requested,
            "roadmap": self.canonical_roadmap_sha,
            "checks": [item.fingerprint for item in self.checks],
        }))

    def preview(self) -> dict[str, object]:
        return {
            "schema": SCHEMA, "kind": "execution_plan",
            "source_commit": self.source_commit,
            "roadmap_sha256": self.canonical_roadmap_sha,
            "selected": list(self.requested),
            "unique_checks": len(self.checks),
            "volume_bindings": sum(len(item.volumes) for item in self.checks),
            "checks": [
                {"path": c.path, "kind": c.kind,
                 "milestones": list(c.milestones), "volumes": list(c.volumes),
                 "source_digest": c.source_digest}
                for c in self.checks
            ],
            "plan_receipt": self.fingerprint,
            "completion_claim": "none",
        }


def _load_roadmap(root: Path) -> tuple[dict, str]:
    roadmap_path = root / "machine/ai_100_large_delivery_milestones.json"
    roadmap, _ = load_json(roadmap_path)
    master, _ = load_json(root / FILES["master_plan"])
    ladder, _ = load_json(root / FILES["advanced_ladder"])
    index, _ = load_json(root / FILES["accountability_index"])
    shas = {}
    for key, path in FILES.items():
        _, shas[key] = load_json(root / path)
    verify(roadmap, master, ladder, index, shas)
    raw = roadmap_path.read_bytes()
    return roadmap, _hash(raw)


def _git_head(root: Path) -> str:
    # Git is invoked using exact fixed arguments, with no shell or user tokens.
    result = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
        capture_output=True, text=True, check=False, timeout=15,
    )
    commit = result.stdout.strip()
    if result.returncode or not _SHA.fullmatch(commit):
        raise MilestoneExecutionError("cannot pin verified git HEAD")
    return commit


def _require_clean_worktree(root: Path) -> None:
    result = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True, text=True, check=False, timeout=30,
    )
    if result.returncode or result.stdout.strip():
        raise MilestoneExecutionError("worktree is dirty; exact-source qualification refused")


def create_execution_plan(
    requested: Sequence[str], *, root: Path = ROOT,
    commit: str | None = None,
    require_clean: bool = True,
) -> ExecutionPlan:
    """Resolve only actual source-declared tests for the 421-volume plan."""
    root = root.resolve()
    names = _safe_selection(requested)
    head = _git_head(root) if commit is None else commit
    if not isinstance(head, str) or not _SHA.fullmatch(head):
        raise MilestoneExecutionError("execution requires exact 40-character source commit")
    if require_clean:
        # When given a test fixture explicit commit, only the real git checkout
        # can be verified as clean. This is not bypassable in actual CLI execution.
        if commit is None:
            _require_clean_worktree(root)
    roadmap, roadmap_sha = _load_roadmap(root)
    by_id = {row["id"]: row for row in roadmap["milestones"]}
    chosen = set(names)
    paths: dict[str, dict[str, object]] = {}
    for milestone in roadmap["milestones"]:
        if milestone["id"] not in chosen:
            continue
        for volume in milestone["volumes"]:
            for test in volume["acceptance_tests"]:
                kind, resolved = _safe_test(test, root)
                row = paths.setdefault(test, {
                    "kind": kind, "path": resolved,
                    "volumes": set(), "milestones": set(),
                })
                if row["kind"] != kind:
                    raise MilestoneExecutionError("conflicting test classification")
                row["volumes"].add(volume["id"])
                row["milestones"].add(milestone["id"])
    if len(paths) > _MAX_TESTS:
        raise MilestoneExecutionError("execution test budget exceeded")
    checks = tuple(
        PlannedCheck(
            path=name, kind=row["kind"],
            volumes=tuple(sorted(row["volumes"])),
            milestones=tuple(sorted(row["milestones"])),
            source_digest=_hash(row["path"].read_bytes()),
        ) for name, row in sorted(paths.items())
    )
    if not checks or {m for item in checks for m in item.milestones} != chosen:
        raise MilestoneExecutionError("selected milestone lacks canonical acceptance tests")
    return ExecutionPlan(head, names, roadmap_sha, checks)


@dataclass(frozen=True, slots=True)
class CheckOutcome:
    check: PlannedCheck
    status: str
    returncode: int | None
    elapsed_ms: int
    output_digest: str
    output_bytes: int
    reason: str
    previous: str
    receipt: str

    @classmethod
    def record(
        cls, check: PlannedCheck, status: str, returncode: int | None,
        elapsed_ms: int, output_digest: str, output_bytes: int,
        reason: str, previous: str,
    ) -> "CheckOutcome":
        if status not in {"passed", "failed", "timed_out", "blocked"}:
            raise MilestoneExecutionError("invalid test execution status")
        if not re.fullmatch(r"[0-9a-f]{64}", output_digest):
            raise MilestoneExecutionError("invalid output evidence digest")
        receipt = _hash(_canonical_json({
            "check": check.fingerprint, "status": status,
            "returncode": returncode, "elapsed_ms": elapsed_ms,
            "output_digest": output_digest, "output_bytes": output_bytes,
            "reason": reason, "previous": previous,
        }))
        return cls(check, status, returncode, elapsed_ms,
                   output_digest, output_bytes, reason, previous, receipt)


@dataclass(frozen=True, slots=True)
class ExecutionReport:
    plan: ExecutionPlan
    outcomes: tuple[CheckOutcome, ...]

    @property
    def fingerprint(self) -> str:
        return _hash(_canonical_json({
            "plan": self.plan.fingerprint,
            "receipts": [outcome.receipt for outcome in self.outcomes],
        }))

    def summary(self) -> dict[str, object]:
        verify_execution_report(self)
        failed = [item.check.path for item in self.outcomes if item.status != "passed"]
        return {
            "schema": SCHEMA, "kind": "execution_report",
            "source_commit": self.plan.source_commit,
            "selected_milestones": list(self.plan.requested),
            "planned_checks": len(self.plan.checks),
            "executed_checks": len(self.outcomes),
            "passed_checks": sum(item.status == "passed" for item in self.outcomes),
            "failed_checks": failed,
            "status": "candidate_checks_passed" if len(self.outcomes) == len(
                self.plan.checks
            ) and not failed else "blocked",
            "independent_milestone_signoff": False,
            "qualifying_milestones": [],
            "checks": [
                {"path": x.check.path, "status": x.status,
                 "returncode": x.returncode, "elapsed_ms": x.elapsed_ms,
                 "output_sha256": x.output_digest, "output_bytes": x.output_bytes,
                 "reason": x.reason, "receipt": x.receipt}
                for x in self.outcomes
            ],
            "report_receipt": self.fingerprint,
        }


def verify_execution_report(report: ExecutionReport) -> None:
    if len(report.outcomes) > len(report.plan.checks):
        raise MilestoneExecutionError("execution contains extra results")
    previous = "0" * 64
    for expected, item in zip(report.plan.checks, report.outcomes):
        if expected != item.check or item.previous != previous:
            raise MilestoneExecutionError("execution reordered or omitted a result")
        signed = CheckOutcome.record(
            item.check, item.status, item.returncode, item.elapsed_ms,
            item.output_digest, item.output_bytes, item.reason, previous,
        )
        if signed != item:
            raise MilestoneExecutionError("test execution receipt was altered")
        previous = item.receipt


RunCheck = Callable[[PlannedCheck, Path, int], tuple[str, int | None, int, str, int, str]]


def _run_check(check: PlannedCheck, root: Path, timeout: int):
    kind, resolved = _safe_test(check.path, root)
    if kind != check.kind or _hash(resolved.read_bytes()) != check.source_digest:
        return "blocked", None, 0, _hash(b""), 0, "test source changed after planning"
    command = ([sys.executable, "-m", "pytest", "-q", "--noconftest", "--rootdir=.",
                check.path] if kind == "pytest"
               else [sys.executable, check.path])
    env = dict(os.environ)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONPATH"] = str(root)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    begun = time.monotonic()
    with tempfile.TemporaryFile() as capture:
        proc = subprocess.Popen(
            command, cwd=root, env=env,
            stdin=subprocess.DEVNULL, stdout=capture, stderr=subprocess.STDOUT,
            shell=False, start_new_session=(os.name == "posix"),
        )
        try:
            code = proc.wait(timeout=timeout)
            status = "passed" if code == 0 else "failed"
            reason = "test process completed" if code == 0 else "test process returned nonzero"
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                import signal
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
            proc.wait()
            code = None
            status, reason = "timed_out", "test deadline exceeded"
        capture.seek(0)
        output = capture.read(_MAX_CAPTURE_BYTES + 1)
        if len(output) > _MAX_CAPTURE_BYTES:
            status = "blocked"
            reason = "test output exceeded capture policy"
        return (
            status, code, max(0, int((time.monotonic() - begun) * 1000)),
            _hash(output), len(output), reason,
        )


def execute_plan(
    plan: ExecutionPlan, *, root: Path = ROOT,
    timeout: int = 120,
    executor: RunCheck | None = None,
    check_worktree: bool = True,
) -> ExecutionReport:
    """Bounded sequential execution; never signs features as implemented."""
    if type(timeout) is not int or not 1 <= timeout <= _MAX_TEST_SECONDS:
        raise MilestoneExecutionError("execution timeout outside bounded policy")
    if check_worktree:
        if _git_head(root) != plan.source_commit:
            raise MilestoneExecutionError("source HEAD changed after planning")
        _require_clean_worktree(root)
        roadmap, digest = _load_roadmap(root)
        if digest != plan.canonical_roadmap_sha or len(roadmap["milestones"]) != 100:
            raise MilestoneExecutionError("canonical milestone plan changed")
    runner = executor or _run_check
    outcomes = []
    previous = "0" * 64
    for check in plan.checks:
        status, code, elapsed, digest, size, reason = runner(check, root, timeout)
        receipt = CheckOutcome.record(
            check, status, code, elapsed, digest, size, reason, previous,
        )
        outcomes.append(receipt)
        previous = receipt.receipt
        if status != "passed":
            # Fail closed and keep the failed step in the evidence chain.
            break
    report = ExecutionReport(plan, tuple(outcomes))
    verify_execution_report(report)
    return report


def _atomic_json(destination: Path, payload: Mapping[str, object]) -> None:
    if destination.exists() and destination.is_symlink():
        raise MilestoneExecutionError("refusing symlink output")
    destination.parent.mkdir(parents=True, exist_ok=True)
    data = _canonical_json(payload) + b"\n"
    with tempfile.NamedTemporaryFile(
        mode="wb", dir=destination.parent, delete=False, prefix=".milestone-",
    ) as temporary:
        name = temporary.name
        temporary.write(data)
        temporary.flush()
        os.fsync(temporary.fileno())
    try:
        os.replace(name, destination)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run canonical MDM milestone acceptance tests against exact HEAD",
    )
    parser.add_argument("--milestone", action="append", dest="milestones")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    if bool(args.all) == bool(args.milestones):
        parser.error("select --all or one or more --milestone MDM-NNN")
    requested = (
        [f"MDM-{i:03d}" for i in range(1, 101)]
        if args.all else args.milestones
    )
    plan = create_execution_plan(requested)
    result = (
        execute_plan(plan, timeout=args.timeout).summary()
        if args.execute else plan.preview()
    )
    if args.report is not None:
        _atomic_json(args.report, result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result.get("status") != "blocked" else 1


if __name__ == "__main__":
    sys.exit(main())
