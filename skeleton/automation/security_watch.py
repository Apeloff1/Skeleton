"""Read-only dependency/security signal triage for unattended maintenance."""

from __future__ import annotations

import json
import os
import subprocess


def _gh(*args: str) -> str:
    result = subprocess.run(["gh", *args], check=True, capture_output=True, text=True)
    return result.stdout


def dependabot_prs(repo: str, limit: int = 50) -> list[dict[str, object]]:
    raw = _gh(
        "pr", "list", "--repo", repo, "--state", "open", "--author", "app/dependabot",
        "--limit", str(limit), "--json", "number,title,url,headRefName,baseRefName",
    )
    return json.loads(raw)


def report(repo: str) -> str:
    prs = dependabot_prs(repo)
    lines = ["## Security Watch Bot", "", f"Open Dependabot PRs: **{len(prs)}**", ""]
    for pr in prs:
        lines.append(
            f"- #{pr['number']} — {pr['title']} — {pr['url']}"
        )
    lines.extend([
        "",
        "This bot is advisory only. It does not merge, approve, execute PR code, disable security checks, or alter dependency policy.",
    ])
    return "\n".join(lines)


def main() -> int:
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        raise SystemExit("GITHUB_REPOSITORY is required")
    print(report(repo))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
