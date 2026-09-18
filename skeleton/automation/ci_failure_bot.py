"""Read-only CI failure triage for unattended repository maintenance."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class FailedRun:
    name: str
    run_id: int
    sha: str
    branch: str
    url: str



def _gh(*args: str) -> str:
    result = subprocess.run(
        ["gh", *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def failed_runs(repo: str, limit: int = 25) -> list[FailedRun]:
    raw = _gh(
        "run",
        "list",
        "--repo",
        repo,
        "--status",
        "failure",
        "--limit",
        str(limit),
        "--json",
        "name,databaseId,headSha,headBranch,url",
    )
    rows = json.loads(raw)
    return [
        FailedRun(
            name=row["name"],
            run_id=int(row["databaseId"]),
            sha=row["headSha"],
            branch=row["headBranch"],
            url=row["url"],
        )
        for row in rows
    ]


def render_report(runs: list[FailedRun]) -> str:
    if not runs:
        return "## CI Failure Bot\n\nNo failed workflow runs were found."

    lines = [
        "## CI Failure Bot",
        "",
        f"Found **{len(runs)}** failed workflow run(s).",
        "",
    ]
    for run in runs:
        lines.extend(
            [
                f"- **{run.name}** — `{run.sha[:12]}` on `{run.branch}`",
                f"  - Run: {run.run_id}",
                f"  - Details: {run.url}",
            ]
        )
    lines.extend(
        [
            "",
            "This bot only observes workflow metadata. It does not checkout or execute failed PR code, modify source, weaken gates, or merge PRs.",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        raise SystemExit("GITHUB_REPOSITORY is required")
    print(render_report(failed_runs(repo)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
