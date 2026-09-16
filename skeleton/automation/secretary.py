"""Repository secretary: understand the plan and route specialist bots.

Routing is deterministic and explainable. The plan is treated as untrusted data;
only its keywords/signals influence which registered specialist is dispatched.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .advanced_bots import ADVANCED_BOTS
from .bot_manager import load_state, record_result, save_state, select_due
from .free_model import redact_secrets

STATE = Path(".skeleton-secretary-state.json")
MAX_PLAN = 18_000
MAX_ASSIGNMENTS = 3

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
    env_plan = os.environ.get("SECRETARY_PLAN", "").strip()
    if env_plan:
        return redact_secrets(env_plan)[:MAX_PLAN]
    repo = os.environ.get("GITHUB_REPOSITORY", "Apeloff1/Skeleton")
    parts: list[str] = []
    try:
        issues = subprocess.check_output(["gh", "issue", "list", "--repo", repo, "--state", "open", "--limit", "30", "--json", "number,title,body,labels"], text=True, timeout=30)
        parts.append("OPEN ISSUES:\n" + issues)
        prs = subprocess.check_output(["gh", "pr", "list", "--repo", repo, "--state", "open", "--limit", "20", "--json", "number,title,body,labels"], text=True, timeout=30)
        parts.append("OPEN PRS:\n" + prs)
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return ""
    return redact_secrets("\n\n".join(parts))[:MAX_PLAN]


def route(plan: str, due: list[str]) -> list[str]:
    text = plan.lower()
    scores = []
    for spec in ADVANCED_BOTS:
        if spec.name not in due:
            continue
        score = sum(1 for word in KEYWORDS.get(spec.name, ()) if word in text)
        if score:
            scores.append((score, spec.risk == "high", spec.name))
    scores.sort(key=lambda x: (-x[0], not x[1], x[2]))
    return [name for _, _, name in scores[:MAX_ASSIGNMENTS]]


def dispatch(plan: str, assignments: list[str]) -> list[dict[str, Any]]:
    results = []
    for name in assignments:
        env = {**os.environ, "SECRETARY_PLAN": plan, "PYTHONPATH": os.getcwd()}
        process = subprocess.run(["python", "-m", "skeleton.automation.specialist_bots", "--bot", name, "--plan", plan], env=env, timeout=900)
        results.append({"bot": name, "returncode": process.returncode})
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", default="")
    args = parser.parse_args()
    plan = redact_secrets(args.plan or _live_plan())[:MAX_PLAN]
    state = load_state()
    due = select_due(state)
    assignments = route(plan, due)
    print(json.dumps({"role": "secretary", "known_specialists": [x.name for x in ADVANCED_BOTS], "due": due, "assignments": assignments}, indent=2))
    if not assignments:
        save_state(state)
        return 0
    results = dispatch(plan, assignments)
    for result in results:
        record_result(state, result["bot"], result["returncode"] == 0)
    save_state(state)
    print(json.dumps({"results": results}, indent=2))
    return 0 if all(x["returncode"] == 0 for x in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
