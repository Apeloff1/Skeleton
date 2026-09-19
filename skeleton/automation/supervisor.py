"""Bounded autonomous repository supervisor.

The supervisor owns observation and planning.  It never executes repository
mutations itself: plans are handed to the existing secretary, which remains
the only dispatcher of specialist workers.  This preserves the authority
chain supervisor -> secretary -> worker while allowing scheduled unattended
operation.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Any

from .free_model import redact_secrets

MAX_CONTEXT_BYTES = 48_000
MAX_PLAN_BYTES = 18_000
MAX_ITEMS = 40
MODEL_TIMEOUT_SECONDS = 90


class SupervisorError(RuntimeError):
    """Supervisor admission or provider failure."""


@dataclass(frozen=True, slots=True)
class SupervisorSnapshot:
    repository: str
    observed_at: int
    issues: tuple[dict[str, Any], ...]
    pull_requests: tuple[dict[str, Any], ...]
    workflow_runs: tuple[dict[str, Any], ...]

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(
            {
                "repository": self.repository,
                "issues": self.issues,
                "pull_requests": self.pull_requests,
                "workflow_runs": self.workflow_runs,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            default=str,
        ).encode()
        return hashlib.sha256(payload).hexdigest()


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
    text = redact_secrets(json.dumps(value, sort_keys=True, ensure_ascii=True, default=str))
    encoded = text.encode("utf-8")
    if len(encoded) > MAX_CONTEXT_BYTES:
        encoded = encoded[:MAX_CONTEXT_BYTES]
        text = encoded.decode("utf-8", errors="ignore")
    return text


def deterministic_plan(snapshot: SupervisorSnapshot) -> str:
    """Safe provider-independent fallback plan.

    The fallback only prioritizes observed work; it cannot synthesize commands.
    """
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
    return json.dumps(payload, sort_keys=True, ensure_ascii=True)


def model_plan(snapshot: SupervisorSnapshot) -> str:
    """Ask the configured model for a plan, falling back deterministically.

    Provider integration is intentionally delegated to the existing free-model
    adapter executable contract.  No model response is ever executed directly;
    secretary keyword routing treats it as untrusted data.
    """
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
    return plan.encode("utf-8")[:MAX_PLAN_BYTES].decode("utf-8", errors="ignore")


def delegate(plan: str, fingerprint: str) -> int:
    """Delegate one admitted plan to secretary; never invoke workers directly."""
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
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    snapshot = observe(repository)
    plan = model_plan(snapshot)
    print(json.dumps({
        "role": "supervisor",
        "repository": repository,
        "snapshot_fingerprint": snapshot.fingerprint,
        "issues": len(snapshot.issues),
        "pull_requests": len(snapshot.pull_requests),
        "workflow_runs": len(snapshot.workflow_runs),
        "plan_bytes": len(plan.encode("utf-8")),
        "delegation": "secretary",
    }, sort_keys=True))
    return delegate(plan, snapshot.fingerprint)


if __name__ == "__main__":
    raise SystemExit(main())
