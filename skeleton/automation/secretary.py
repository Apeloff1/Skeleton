"""Repository Secretary: admit Supervisor plans and isolate registered workers.

The Secretary is the only delegation boundary between planning and execution.
Supervisor/model/repository text is untrusted data: it may influence bounded
routing but cannot select an executable, Python module, permission, token, or
arbitrary worker.

Each selected worker receives a fresh detached git worktree at the exact
Supervisor base SHA.  Multiple workers therefore cannot accidentally build on
one another's branches or mutations.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .advanced_bots import ADVANCED_BOTS
from .bot_manager import (
    load_state,
    record_result,
    save_state,
    select_specialists_due,
)
from .free_model import redact_secrets
from .supervisor_runtime import (
    ExecutionIdentity,
    SupervisorRuntimeError,
    require_exact_head,
    require_remote_base_unchanged,
    sanitized_worker_env,
    validate_fingerprint,
)

MAX_PLAN = 18_000
MAX_ASSIGNMENTS = 3
MAX_ENVELOPE_AGE_SECONDS = 2 * 60 * 60
MAX_ENCODED_ENVELOPE = 32_000

KEYWORDS = {
    "root-cause": (
        "ci",
        "workflow",
        "build",
        "failure",
        "failed",
        "actions",
    ),
    "dependency-guardian": (
        "dependabot",
        "dependency",
        "cve",
        "vulnerability",
        "package",
        "lockfile",
    ),
    "regression-hunter": (
        "regression",
        "flaky",
        "failing test",
        "test failure",
    ),
    "architecture-reviewer": (
        "architecture",
        "subsystem",
        "refactor",
        "drift",
        "large pr",
    ),
    "security-auditor": (
        "security",
        "code scanning",
        "secret",
        "cors",
        "auth",
        "ssrf",
        "sast",
    ),
    "performance-sentinel": (
        "performance",
        "benchmark",
        "timeout",
        "slow",
        "latency",
    ),
    "release-guardian": (
        "release",
        "version",
        "publish",
        "artifact",
        "provenance",
    ),
    "documentation-guardian": (
        "docs",
        "documentation",
        "readme",
        "drift",
    ),
    "integration-sentinel": (
        "integration",
        "contract",
        "cross-subsystem",
        "e2e",
        "arm64",
    ),
    "pr-reviewer": (
        "pull request",
        "pr ",
        "review",
        "reviewer",
    ),
    "test-gap": (
        "coverage",
        "missing test",
        "test gap",
        "uncovered",
    ),
    "api-contract": (
        "api",
        "schema",
        "openapi",
        "contract",
        "endpoint",
    ),
}


class SecretaryAdmissionError(ValueError):
    """Delegation failed the Secretary trust boundary."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SecretaryAdmissionError(
                f"duplicate supervisor delegation field: {key}"
            )
        result[key] = value
    return result


def _live_plan() -> str:
    """Compatibility path for explicit local/manual Secretary invocation."""
    supplied = os.environ.get("SECRETARY_PLAN", "").strip()
    if supplied:
        return redact_secrets(supplied)[:MAX_PLAN]

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not repo:
        return ""

    parts: list[str] = []
    try:
        issues = subprocess.check_output(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                repo,
                "--state",
                "open",
                "--limit",
                "30",
                "--json",
                "number,title,body,labels",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        prs = subprocess.check_output(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                repo,
                "--state",
                "open",
                "--limit",
                "20",
                "--json",
                "number,title,body,labels",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        parts.extend(
            [
                "OPEN ISSUES:\n" + issues,
                "OPEN PRS:\n" + prs,
            ]
        )
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ):
        return ""
    return redact_secrets("\n\n".join(parts))[:MAX_PLAN]


def decode_delegation(
    encoded: str,
    *,
    repository: str,
    expected_execution: ExecutionIdentity,
    now: int | None = None,
) -> tuple[str, str, ExecutionIdentity]:
    """Decode and bind a version-2 cross-job Supervisor custody envelope."""
    if not encoded or len(encoded) > MAX_ENCODED_ENVELOPE:
        raise SecretaryAdmissionError(
            "invalid supervisor delegation size"
        )

    try:
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > MAX_PLAN + 6_000:
            raise SecretaryAdmissionError(
                "supervisor delegation too large"
            )
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
        )
    except (
        ValueError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise SecretaryAdmissionError(
            "invalid supervisor delegation encoding"
        ) from exc

    expected_fields = {
        "version",
        "repository",
        "snapshot_fingerprint",
        "observed_at",
        "plan",
        "execution",
        "execution_fingerprint",
    }
    if not isinstance(value, dict) or set(value) != expected_fields:
        raise SecretaryAdmissionError(
            "invalid supervisor delegation shape"
        )
    if value.get("version") != 2:
        raise SecretaryAdmissionError(
            "unsupported supervisor delegation"
        )

    envelope_repo = value.get("repository")
    if envelope_repo != repository:
        raise SecretaryAdmissionError(
            "cross-repository supervisor delegation rejected"
        )

    fingerprint = value.get("snapshot_fingerprint")
    try:
        fingerprint = validate_fingerprint(fingerprint)
    except SupervisorRuntimeError as exc:
        raise SecretaryAdmissionError(
            "invalid supervisor snapshot fingerprint"
        ) from exc

    observed_at = value.get("observed_at")
    current = int(time.time()) if now is None else now
    if isinstance(observed_at, bool) or not isinstance(observed_at, int):
        raise SecretaryAdmissionError(
            "invalid supervisor observation time"
        )
    age = current - observed_at
    if age < -300 or age > MAX_ENVELOPE_AGE_SECONDS:
        raise SecretaryAdmissionError(
            "stale supervisor delegation rejected"
        )

    plan = value.get("plan")
    if not isinstance(plan, str):
        raise SecretaryAdmissionError("invalid supervisor plan")
    plan = redact_secrets(plan).strip()
    if not plan or len(plan.encode("utf-8")) > MAX_PLAN:
        raise SecretaryAdmissionError(
            "invalid supervisor plan size"
        )

    raw_execution = value.get("execution")
    if not isinstance(raw_execution, dict):
        raise SecretaryAdmissionError(
            "invalid supervisor execution identity"
        )
    if set(raw_execution) != {
        "repository",
        "base_sha",
        "default_branch",
        "run_id",
        "run_attempt",
    }:
        raise SecretaryAdmissionError(
            "invalid supervisor execution shape"
        )

    try:
        envelope_execution = ExecutionIdentity(
            repository=raw_execution["repository"],
            base_sha=raw_execution["base_sha"],
            default_branch=raw_execution["default_branch"],
            run_id=raw_execution["run_id"],
            run_attempt=raw_execution["run_attempt"],
        )
    except (KeyError, SupervisorRuntimeError) as exc:
        raise SecretaryAdmissionError(
            "invalid supervisor execution identity"
        ) from exc

    if envelope_execution != expected_execution:
        raise SecretaryAdmissionError(
            "supervisor delegation execution replay rejected"
        )
    if value.get("execution_fingerprint") != envelope_execution.fingerprint:
        raise SecretaryAdmissionError(
            "supervisor execution fingerprint mismatch"
        )

    return plan, fingerprint, envelope_execution


def _supervisor_provenance(
    execution: ExecutionIdentity,
) -> str | None:
    """Validate provenance for the explicit local/manual compatibility path."""
    if os.environ.get("SUPERVISOR_DELEGATION") != "1":
        return None

    fingerprint = os.environ.get(
        "SUPERVISOR_SNAPSHOT_FINGERPRINT",
        "",
    )
    try:
        validate_fingerprint(fingerprint)
    except SupervisorRuntimeError as exc:
        raise SecretaryAdmissionError(
            "invalid supervisor snapshot fingerprint"
        ) from exc

    supplied = ExecutionIdentity.from_env()
    if supplied != execution:
        raise SecretaryAdmissionError(
            "manual supervisor execution identity mismatch"
        )
    return fingerprint


def route(plan: str, due: list[str]) -> list[str]:
    """Score due registered specialists without allowing model-selected code."""
    text = plan.lower()
    due_set = set(due)
    registered = {spec.name for spec in ADVANCED_BOTS}
    due_set &= registered

    scored: list[tuple[int, bool, str]] = []
    for spec in ADVANCED_BOTS:
        if spec.name not in due_set:
            continue
        score = sum(
            1
            for word in KEYWORDS.get(spec.name, ())
            if word in text
        )
        if score:
            scored.append(
                (
                    score,
                    spec.risk == "high",
                    spec.name,
                )
            )

    scored.sort(
        key=lambda item: (
            -item[0],
            not item[1],
            item[2],
        )
    )
    return [
        name
        for _score, _high, name in scored[:MAX_ASSIGNMENTS]
    ]


def _remove_worktree(
    path: Path,
    *,
    repo_root: Path,
) -> None:
    """Best-effort cleanup that never masks the worker result."""
    try:
        subprocess.run(
            [
                "git",
                "worktree",
                "remove",
                "--force",
                str(path),
            ],
            cwd=repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
            check=False,
        )
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _dispatch_one(
    plan: str,
    name: str,
    *,
    supervisor_fingerprint: str,
    execution: ExecutionIdentity,
) -> dict[str, Any]:
    """Run one worker in a detached worktree rooted at the admitted base."""
    repo_root = Path.cwd().resolve()
    require_exact_head(execution.base_sha, cwd=repo_root)
    require_remote_base_unchanged(execution)

    runner_temp = Path(
        os.environ.get("RUNNER_TEMP", tempfile.gettempdir())
    )
    runner_temp.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=f"secretary-{name}-",
        dir=runner_temp,
    ) as temporary:
        worktree = Path(temporary) / "worktree"
        try:
            subprocess.run(
                [
                    "git",
                    "worktree",
                    "add",
                    "--detach",
                    str(worktree),
                    execution.base_sha,
                ],
                cwd=repo_root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=60,
                check=True,
            )

            env = sanitized_worker_env(os.environ)
            env.update(
                {
                    "SECRETARY_PLAN": plan,
                    "SECRETARY_WORKER": name,
                    "SECRETARY_DELEGATION": "1",
                    "SUPERVISOR_SNAPSHOT_FINGERPRINT": (
                        supervisor_fingerprint
                    ),
                    "SUPERVISOR_BASE_SHA": execution.base_sha,
                    "SUPERVISOR_DEFAULT_BRANCH": (
                        execution.default_branch
                    ),
                    "SUPERVISOR_RUN_ID": execution.run_id,
                    "SUPERVISOR_RUN_ATTEMPT": execution.run_attempt,
                    "SUPERVISOR_EXECUTION_FINGERPRINT": (
                        execution.fingerprint
                    ),
                    "PYTHONPATH": str(worktree),
                    "GITHUB_WORKSPACE": str(worktree),
                }
            )

            process = subprocess.run(
                [
                    "python",
                    "-m",
                    "skeleton.automation.specialist_bots",
                    "--bot",
                    name,
                    "--plan",
                    plan,
                ],
                cwd=worktree,
                env=env,
                timeout=900,
                check=False,
            )
            return {
                "bot": name,
                "returncode": process.returncode,
                "isolated": True,
            }
        except (
            OSError,
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            SupervisorRuntimeError,
        ):
            return {
                "bot": name,
                "returncode": 1,
                "isolated": True,
            }
        finally:
            _remove_worktree(
                worktree,
                repo_root=repo_root,
            )


def dispatch(
    plan: str,
    assignments: list[str],
    supervisor_fingerprint: str,
    execution: ExecutionIdentity,
) -> list[dict[str, Any]]:
    """Dispatch registered workers with strict assignment and isolation budgets."""
    registered = {spec.name for spec in ADVANCED_BOTS}
    if len(assignments) > MAX_ASSIGNMENTS:
        raise SecretaryAdmissionError(
            "assignment budget exceeded"
        )
    if len(assignments) != len(set(assignments)):
        raise SecretaryAdmissionError(
            "duplicate worker assignment"
        )

    unknown = set(assignments) - registered
    if unknown:
        raise SecretaryAdmissionError(
            "unregistered worker assignment"
        )

    try:
        validate_fingerprint(supervisor_fingerprint)
    except SupervisorRuntimeError as exc:
        raise SecretaryAdmissionError(
            "invalid dispatch snapshot fingerprint"
        ) from exc

    results: list[dict[str, Any]] = []
    for name in assignments:
        results.append(
            _dispatch_one(
                plan,
                name,
                supervisor_fingerprint=supervisor_fingerprint,
                execution=execution,
            )
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", default="")
    parser.add_argument("--delegation-b64", default="")
    args = parser.parse_args()

    try:
        execution = ExecutionIdentity.from_env()
        require_exact_head(execution.base_sha)
        require_remote_base_unchanged(execution)
    except SupervisorRuntimeError as exc:
        raise SecretaryAdmissionError(
            f"invalid immutable Secretary execution: {exc}"
        ) from exc

    if args.delegation_b64:
        (
            plan,
            supervisor_fingerprint,
            envelope_execution,
        ) = decode_delegation(
            args.delegation_b64,
            repository=execution.repository,
            expected_execution=execution,
        )
        if envelope_execution != execution:
            raise SecretaryAdmissionError(
                "Secretary execution changed after admission"
            )
    else:
        plan = redact_secrets(
            args.plan or _live_plan()
        )[:MAX_PLAN]
        supervisor_fingerprint = _supervisor_provenance(
            execution
        )

    if not plan:
        raise SecretaryAdmissionError(
            "Secretary received no admitted plan"
        )
    if not supervisor_fingerprint:
        raise SecretaryAdmissionError(
            "Secretary requires Supervisor custody"
        )

    state = load_state()
    due = select_specialists_due(state)
    assignments = route(plan, due)

    print(
        json.dumps(
            {
                "role": "secretary",
                "repository": execution.repository,
                "base_sha": execution.base_sha,
                "execution_fingerprint": execution.fingerprint,
                "supervisor_snapshot_fingerprint": (
                    supervisor_fingerprint
                ),
                "known_specialists": [
                    spec.name for spec in ADVANCED_BOTS
                ],
                "specialists_due": due,
                "assignments": assignments,
                "worker_isolation": "detached-worktree",
            },
            indent=2,
            sort_keys=True,
        )
    )

    if not assignments:
        save_state(state)
        return 0

    results = dispatch(
        plan,
        assignments,
        supervisor_fingerprint,
        execution,
    )
    for result in results:
        record_result(
            state,
            result["bot"],
            result["returncode"] == 0,
        )
    save_state(state)

    print(
        json.dumps(
            {"results": results},
            indent=2,
            sort_keys=True,
        )
    )
    return (
        0
        if all(result["returncode"] == 0 for result in results)
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
