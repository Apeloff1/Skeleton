"""Repository secretary: admit supervisor plans and route registered workers.

The secretary is the only delegation boundary between planning and execution.
Supervisor/model/repository text is untrusted data: it may influence bounded
routing but cannot select an executable, Python module, permission, or token.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from .advanced_bots import ADVANCED_BOTS
from .bot_manager import load_state, record_result, save_state, select_specialists_due
from .free_model import redact_secrets

MAX_PLAN = 18_000
MAX_ASSIGNMENTS = 3
MAX_ENVELOPE_AGE_SECONDS = 2 * 60 * 60
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}$")

KEYWORDS = {
    "root-cause": ("ci", "workflow", "build", "failure", "failed", "actions"),
    "dependency-guardian": ("dependabot", "dependency", "cve", "vulnerability", "package", "lockfile"),
    "regression-hunter": ("regression", "flaky", "failing test", "test failure"),
    "architecture-reviewer": ("architecture", "subsystem", "refactor", "drift", "large pr"),
    "security-auditor": ("security", "code scanning", "secret", "cors", "auth", "ssrf"),
    "performance-sentinel": ("performance", "benchmark", "timeout", "slow", "latency"),
    "release-guardian": ("release", "version", "publish", "artifact", "provenance"),
    "documentation-guardian": ("docs", "documentation", "readme", "drift"),
    "integration-sentinel": ("integration", "contract", "cross-subsystem", "e2e"),
    "pr-reviewer": ("pull request", "pr ", "review", "reviewer"),
    "test-gap": ("coverage", "missing test", "test gap", "uncovered"),
    "api-contract": ("api", "schema", "openapi", "contract", "endpoint"),
}


class SecretaryAdmissionError(ValueError):
    """Delegation failed the Secretary's trust boundary."""


def _live_plan() -> str:
    supplied = os.environ.get("SECRETARY_PLAN", "").strip()
    if supplied:
        return redact_secrets(supplied)[:MAX_PLAN]
    repo = os.environ.get("GITHUB_REPOSITORY", "Apeloff1/Skeleton")
    parts: list[str] = []
    try:
        issues = subprocess.check_output(["gh", "issue", "list", "--repo", repo, "--state", "open", "--limit", "30", "--json", "number,title,body,labels"], text=True, timeout=30)
        prs = subprocess.check_output(["gh", "pr", "list", "--repo", repo, "--state", "open", "--limit", "20", "--json", "number,title,body,labels"], text=True, timeout=30)
        parts.extend(["OPEN ISSUES:\n" + issues, "OPEN PRS:\n" + prs])
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""
    return redact_secrets("\n\n".join(parts))[:MAX_PLAN]


def decode_delegation(encoded: str, *, repository: str, now: int | None = None) -> tuple[str, str]:
    """Decode and validate the cross-job Supervisor custody envelope."""
    if not encoded or len(encoded) > 32_000:
        raise SecretaryAdmissionError("invalid supervisor delegation size")
    try:
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > MAX_PLAN + 2_000:
            raise SecretaryAdmissionError("supervisor delegation too large")
        value = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SecretaryAdmissionError("invalid supervisor delegation encoding") from exc
    if not isinstance(value, dict) or value.get("version") != 1:
        raise SecretaryAdmissionError("unsupported supervisor delegation")
    envelope_repo = value.get("repository")
    if not isinstance(envelope_repo, str) or _REPOSITORY_RE.fullmatch(envelope_repo) is None:
        raise SecretaryAdmissionError("invalid supervisor repository")
    if envelope_repo != repository:
        raise SecretaryAdmissionError("cross-repository supervisor delegation rejected")
    fingerprint = value.get("snapshot_fingerprint")
    if not isinstance(fingerprint, str) or _FINGERPRINT_RE.fullmatch(fingerprint) is None:
        raise SecretaryAdmissionError("invalid supervisor snapshot fingerprint")
    observed_at = value.get("observed_at")
    current = int(time.time()) if now is None else now
    if isinstance(observed_at, bool) or not isinstance(observed_at, int):
        raise SecretaryAdmissionError("invalid supervisor observation time")
    age = current - observed_at
    if age < -300 or age > MAX_ENVELOPE_AGE_SECONDS:
        raise SecretaryAdmissionError("stale supervisor delegation rejected")
    plan = value.get("plan")
    if not isinstance(plan, str):
        raise SecretaryAdmissionError("invalid supervisor plan")
    plan = redact_secrets(plan).strip()
    if not plan or len(plan.encode("utf-8")) > MAX_PLAN:
        raise SecretaryAdmissionError("invalid supervisor plan size")
    return plan, fingerprint


def _supervisor_provenance() -> str | None:
    """Validate provenance for local/manual Supervisor delegation."""
    if os.environ.get("SUPERVISOR_DELEGATION") != "1":
        return None
    fingerprint = os.environ.get("SUPERVISOR_SNAPSHOT_FINGERPRINT", "")
    if _FINGERPRINT_RE.fullmatch(fingerprint) is None:
        raise SecretaryAdmissionError("invalid supervisor snapshot fingerprint")
    return fingerprint


def route(plan: str, due: list[str]) -> list[str]:
    text = plan.lower()
    due_set = set(due)
    scored: list[tuple[int, bool, str]] = []
    for spec in ADVANCED_BOTS:
        if spec.name not in due_set:
            continue
        score = sum(1 for word in KEYWORDS.get(spec.name, ()) if word in text)
        if score:
            scored.append((score, spec.risk == "high", spec.name))
    scored.sort(key=lambda x: (-x[0], not x[1], x[2]))
    return [name for _, _, name in scored[:MAX_ASSIGNMENTS]]


def dispatch(plan: str, assignments: list[str], supervisor_fingerprint: str | None = None) -> list[dict[str, Any]]:
    registered = {spec.name for spec in ADVANCED_BOTS}
    if len(assignments) > MAX_ASSIGNMENTS:
        raise SecretaryAdmissionError("assignment budget exceeded")
    if len(assignments) != len(set(assignments)):
        raise SecretaryAdmissionError("duplicate worker assignment")
    unknown = set(assignments) - registered
    if unknown:
        raise SecretaryAdmissionError("unregistered worker assignment")
    results: list[dict[str, Any]] = []
    for name in assignments:
        env = {
            **os.environ,
            "SECRETARY_PLAN": plan,
            "SECRETARY_WORKER": name,
            "SECRETARY_DELEGATION": "1",
            "PYTHONPATH": os.getcwd(),
        }
        if supervisor_fingerprint:
            env["SUPERVISOR_SNAPSHOT_FINGERPRINT"] = supervisor_fingerprint
        try:
            process = subprocess.run(
                ["python", "-m", "skeleton.automation.specialist_bots", "--bot", name, "--plan", plan],
                env=env,
                timeout=900,
            )
            returncode = process.returncode
        except (OSError, subprocess.TimeoutExpired):
            returncode = 1
        results.append({"bot": name, "returncode": returncode})
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", default="")
    parser.add_argument("--delegation-b64", default="")
    args = parser.parse_args()
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if args.delegation_b64:
        plan, supervisor_fingerprint = decode_delegation(args.delegation_b64, repository=repository)
    else:
        plan = redact_secrets(args.plan or _live_plan())[:MAX_PLAN]
        supervisor_fingerprint = _supervisor_provenance()
    state = load_state()
    due = select_specialists_due(state)
    assignments = route(plan, due)
    print(json.dumps({
        "role": "secretary",
        "supervisor_snapshot_fingerprint": supervisor_fingerprint,
        "known_specialists": [x.name for x in ADVANCED_BOTS],
        "specialists_due": due,
        "assignments": assignments,
    }, indent=2))
    if not assignments:
        save_state(state)
        return 0
    results = dispatch(plan, assignments, supervisor_fingerprint)
    for result in results:
        record_result(state, result["bot"], result["returncode"] == 0)
    save_state(state)
    print(json.dumps({"results": results}, indent=2))
    return 0 if all(x["returncode"] == 0 for x in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
