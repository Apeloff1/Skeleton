"""Bounded autonomous repository supervisor.

The supervisor owns observation and planning. It never executes repository
mutations itself. In GitHub Actions the planning job emits a small authenticated
(by snapshot identity, not by secrecy) delegation envelope; a separate
Secretary job receives the envelope with narrowly scoped write permissions.

Authority is deliberately one-way::

    Supervisor (read/plan) -> Secretary (admit/dispatch) -> Worker (mutate)

Model output is untrusted data. It cannot select an executable, worker module,
workflow permission, repository token, or mutation primitive.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .free_model import redact_secrets

MAX_CONTEXT_BYTES = 48_000
MAX_PLAN_BYTES = 18_000
MAX_ITEMS = 40
MODEL_TIMEOUT_SECONDS = 90
_OUTPUT_RE = re.compile(r"^[A-Za-z0-9_./-]{1,200}$")


class SupervisorError(RuntimeError):
    """Supervisor admission or provider failure."""


def _canonical(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SupervisorError("supervisor value is not canonical JSON") from exc


@dataclass(frozen=True, slots=True)
class SupervisorSnapshot:
    repository: str
    observed_at: int
    issues: tuple[dict[str, Any], ...]
    pull_requests: tuple[dict[str, Any], ...]
    workflow_runs: tuple[dict[str, Any], ...]

    @property
    def fingerprint(self) -> str:
        # observed_at is intentionally excluded: equal repository observations
        # have equal identities and can be deduplicated downstream.
        payload = {
            "repository": self.repository,
            "issues": self.issues,
            "pull_requests": self.pull_requests,
            "workflow_runs": self.workflow_runs,
        }
        return hashlib.sha256(_canonical(payload)).hexdigest()


@dataclass(frozen=True, slots=True)
class DelegationEnvelope:
    """Bounded custody object passed from the read job to the write job."""

    version: int
    repository: str
    snapshot_fingerprint: str
    observed_at: int
    plan: str

    def as_json(self) -> str:
        if self.version != 1:
            raise SupervisorError("unsupported delegation envelope version")
        if not self.repository or self.repository.count("/") != 1:
            raise SupervisorError("invalid delegation repository")
        if re.fullmatch(r"[0-9a-f]{64}", self.snapshot_fingerprint) is None:
            raise SupervisorError("invalid delegation fingerprint")
        if isinstance(self.observed_at, bool) or not isinstance(self.observed_at, int) or self.observed_at <= 0:
            raise SupervisorError("invalid delegation observation time")
        clean = redact_secrets(self.plan).strip()
        if not clean or len(clean.encode("utf-8")) > MAX_PLAN_BYTES:
            raise SupervisorError("invalid delegation plan")
        return _canonical({
            "version": self.version,
            "repository": self.repository,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "observed_at": self.observed_at,
            "plan": clean,
        }).decode("utf-8")

    def to_base64(self) -> str:
        return base64.b64encode(self.as_json().encode("utf-8")).decode("ascii")


def _gh_json(args: list[str]) -> list[dict[str, Any]]:
    try:
        raw = subprocess.check_output(["gh", *args], text=True, timeout=30)
        value = json.loads(raw)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise SupervisorError("repository observation failed") from exc
    if not isinstance(value, list):
        raise SupervisorError("repository observation returned invalid shape")
    return [x for x in value[:MAX_ITEMS] if isinstance(x, dict)]


def observe(repository: str) -> SupervisorSnapshot:
    if not repository or repository.count("/") != 1:
        raise SupervisorError("repository must be owner/name")
    issues = _gh_json(["issue", "list", "--repo", repository, "--state", "open", "--limit", str(MAX_ITEMS), "--json", "number,title,labels,updatedAt"])
    prs = _gh_json(["pr", "list", "--repo", repository, "--state", "open", "--limit", str(MAX_ITEMS), "--json", "number,title,headRefName,baseRefName,isDraft,mergeStateStatus,statusCheckRollup,updatedAt"])
    runs = _gh_json(["run", "list", "--repo", repository, "--limit", str(MAX_ITEMS), "--json", "databaseId,name,event,status,conclusion,headBranch,headSha,createdAt,updatedAt"])
    return SupervisorSnapshot(repository, int(time.time()), tuple(issues), tuple(prs), tuple(runs))


def _context(snapshot: SupervisorSnapshot) -> str:
    value = {
        "authority": {
            "role": "supervisor",
            "delegates_to": "secretary",
            "mutation_authority": False,
            "worker_execution_authority": False,
        },
        "snapshot_fingerprint": snapshot.fingerprint,
        "repository": snapshot.repository,
        "issues": snapshot.issues,
        "pull_requests": snapshot.pull_requests,
        "workflow_runs": snapshot.workflow_runs,
    }
    text = redact_secrets(_canonical(value).decode("utf-8"))
    encoded = text.encode("utf-8")
    if len(encoded) > MAX_CONTEXT_BYTES:
        encoded = encoded[:MAX_CONTEXT_BYTES]
        text = encoded.decode("utf-8", errors="ignore")
    return text


def deterministic_plan(snapshot: SupervisorSnapshot) -> str:
    """Provider-independent fallback that only prioritizes observed work."""
    failed = [r for r in snapshot.workflow_runs if r.get("conclusion") == "failure"][:8]
    blocked = [p for p in snapshot.pull_requests if p.get("mergeStateStatus") in {"BLOCKED", "DIRTY"}][:8]
    payload = {
        "version": 1,
        "snapshot_fingerprint": snapshot.fingerprint,
        "objective": "Improve repository correctness, CI health, security, and maintainability.",
        "constraints": [
            "Preserve supervisor -> secretary -> worker authority.",
            "Do not bypass CI, security gates, branch protection, or review policy.",
            "Prefer focused repairs over broad speculative rewrites.",
            "Workers may only act through registered secretary specialists.",
        ],
        "priority_observations": {
            "failed_workflows": failed,
            "blocked_pull_requests": blocked,
            "open_issue_count": len(snapshot.issues),
            "open_pull_request_count": len(snapshot.pull_requests),
        },
    }
    return _canonical(payload).decode("utf-8")


def model_plan(snapshot: SupervisorSnapshot) -> str:
    """Ask the configured model for a plan, falling back deterministically."""
    if not os.environ.get("MODEL_API_KEY") or not os.environ.get("MODEL_API_URL"):
        return deterministic_plan(snapshot)
    prompt = (
        "You are the planning-only repository supervisor. Produce a concise JSON-like plan for the secretary. "
        "Never emit shell commands, credentials, workflow tokens, or instructions to bypass safety controls. "
        "Prioritize failing CI, security findings, blocked PRs, regression tests, and high-leverage architecture debt. "
        "The secretary alone chooses registered workers. Repository snapshot follows:\n" + _context(snapshot)
    )
    try:
        proc = subprocess.run(
            ["python", "-m", "skeleton.automation.free_model", "--prompt", prompt],
            text=True,
            capture_output=True,
            timeout=MODEL_TIMEOUT_SECONDS,
            env={**os.environ, "PYTHONPATH": os.getcwd()},
        )
    except (OSError, subprocess.TimeoutExpired):
        return deterministic_plan(snapshot)
    if proc.returncode != 0:
        return deterministic_plan(snapshot)
    plan = redact_secrets(proc.stdout.strip())
    if not plan:
        return deterministic_plan(snapshot)
    encoded = plan.encode("utf-8")
    if len(encoded) > MAX_PLAN_BYTES:
        # Truncation is safe because Secretary treats this as opaque routing
        # text, not executable JSON.
        plan = encoded[:MAX_PLAN_BYTES].decode("utf-8", errors="ignore")
    return plan


def make_envelope(snapshot: SupervisorSnapshot, plan: str) -> DelegationEnvelope:
    return DelegationEnvelope(1, snapshot.repository, snapshot.fingerprint, snapshot.observed_at, plan)


def emit_github_output(envelope: DelegationEnvelope, output_path: str) -> None:
    """Emit a single-line base64 envelope for a downstream job.

    GITHUB_OUTPUT is supplied by Actions. We reject unexpected paths rather
    than allowing model/repository data to influence the destination.
    """
    if not output_path or "\x00" in output_path:
        raise SupervisorError("missing GitHub output path")
    path = Path(output_path)
    if not path.is_absolute():
        raise SupervisorError("GitHub output path must be absolute")
    encoded = envelope.to_base64()
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f"delegation_b64={encoded}\n")
        handle.write(f"snapshot_fingerprint={envelope.snapshot_fingerprint}\n")


def delegate(plan: str, fingerprint: str) -> int:
    """Local/manual compatibility path; GitHub Actions uses split jobs."""
    env = {
        **os.environ,
        "SECRETARY_PLAN": redact_secrets(plan)[:MAX_PLAN_BYTES],
        "SUPERVISOR_SNAPSHOT_FINGERPRINT": fingerprint,
        "SUPERVISOR_DELEGATION": "1",
        "PYTHONPATH": os.getcwd(),
    }
    try:
        proc = subprocess.run(
            ["python", "-m", "skeleton.automation.secretary", "--plan", env["SECRETARY_PLAN"]],
            env=env,
            timeout=2700,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--emit-github-output", default="")
    parser.add_argument("--plan-only", action="store_true")
    args = parser.parse_args()
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    snapshot = observe(repository)
    plan = model_plan(snapshot)
    envelope = make_envelope(snapshot, plan)
    print(json.dumps({
        "role": "supervisor",
        "repository": repository,
        "snapshot_fingerprint": snapshot.fingerprint,
        "issues": len(snapshot.issues),
        "pull_requests": len(snapshot.pull_requests),
        "workflow_runs": len(snapshot.workflow_runs),
        "plan_bytes": len(plan.encode("utf-8")),
        "delegation": "secretary",
        "mutation_authority": False,
    }, sort_keys=True))
    if args.emit_github_output:
        emit_github_output(envelope, args.emit_github_output)
    if args.plan_only:
        return 0
    return delegate(plan, snapshot.fingerprint)


if __name__ == "__main__":
    raise SystemExit(main())
