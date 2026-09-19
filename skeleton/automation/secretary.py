"""Repository secretary: admit supervisor plans and route registered workers.

The secretary is the delegation boundary between planning and execution.  Model
or repository text is untrusted data; it can influence deterministic routing
but cannot select arbitrary executables or elevate worker authority.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from typing import Any

from .advanced_bots import ADVANCED_BOTS
from .bot_manager import load_state, record_result, save_state, select_specialists_due
from .free_model import redact_secrets

MAX_PLAN = 18_000
MAX_ASSIGNMENTS = 3
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")

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


def _supervisor_provenance() -> str | None:
    """Validate provenance when invoked through the autonomous supervisor."""
    if os.environ.get("SUPERVISOR_DELEGATION") != "1":
        return None
    fingerprint = os.environ.get("SUPERVISOR_SNAPSHOT_FINGERPRINT", "")
    if _FINGERPRINT_RE.fullmatch(fingerprint) is None:
        raise ValueError("invalid supervisor snapshot fingerprint")
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
        raise ValueError("assignment budget exceeded")
    if len(assignments) != len(set(assignments)):
        raise ValueError("duplicate worker assignment")
    unknown = set(assignments) - registered
    if unknown:
        raise ValueError("unregistered worker assignment")
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
    args = parser.parse_args()
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
