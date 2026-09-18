"""Safe, repository-native maintenance bots for scheduled unattended runs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class BotResult:
    name: str
    changed: int
    notes: tuple[str, ...] = ()


class Gh:
    def __init__(self, repo: str, timeout: int = 30) -> None:
        self.repo = repo
        self.timeout = timeout

    def run(self, args: Sequence[str], *, check: bool = True) -> str:
        p = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=self.timeout, check=check)
        return p.stdout

    def json(self, args: Sequence[str]) -> Any:
        return json.loads(self.run(args) or "null")

    def issues(self, limit: int = 100) -> list[Mapping[str, Any]]:
        data = self.json(["issue", "list", "--repo", self.repo, "--state", "open", "--limit", str(limit), "--json", "number,title,body,labels,updatedAt,author,url"])
        return data if isinstance(data, list) else []

    def prs(self, limit: int = 100) -> list[Mapping[str, Any]]:
        data = self.json(["pr", "list", "--repo", self.repo, "--state", "open", "--limit", str(limit), "--json", "number,title,body,labels,author,url,headRefName,baseRefName"])
        return data if isinstance(data, list) else []

    def add_label(self, number: int, label: str) -> bool:
        result = subprocess.run(["gh", "issue", "edit", str(number), "--repo", self.repo, "--add-label", label], capture_output=True, text=True, timeout=self.timeout)
        return result.returncode == 0

    def comment(self, number: int, body: str) -> None:
        self.run(["issue", "comment", str(number), "--repo", self.repo, "--body", body])

    def create_issue(self, title: str, body: str, labels: Sequence[str]) -> int:
        args = ["issue", "create", "--repo", self.repo, "--title", title, "--body", body]
        for label in labels:
            args.extend(["--label", label])
        created = self.run(args).strip()
        try:
            number = int(created.rstrip("/").rsplit("/", 1)[-1])
        except (TypeError, ValueError) as exc:
            raise RuntimeError("created issue URL did not contain a numeric issue number") from exc
        if number <= 0:
            raise RuntimeError("created issue number must be positive")
        return number

    def find_issue(self, title: str) -> Mapping[str, Any] | None:
        data = self.json([
            "issue", "list", "--repo", self.repo, "--state", "all",
            "--search", f"{title} in:title", "--limit", "100",
            "--json", "number,title,state",
        ])
        if not isinstance(data, list):
            return None
        exact = [
            item
            for item in data
            if isinstance(item, Mapping)
            and str(item.get("title", "")) == title
            and isinstance(item.get("number"), int)
        ]
        return max(exact, key=lambda item: int(item["number"])) if exact else None

    def close_issue(self, number: int) -> None:
        self.run([
            "api", "--method", "PATCH",
            f"repos/{self.repo}/issues/{number}",
            "-f", "state=closed",
        ])


def labels_for(text: str) -> tuple[str, ...]:
    value = text.lower()
    labels: list[str] = []
    if any(x in value for x in ("dependabot", "dependency", "cve", "vulnerability", "security")):
        labels.append("security")
    if any(x in value for x in ("ci", "workflow", "action", "build", "test", "merge readiness")):
        labels.append("ci")
    if any(x in value for x in ("docker", "container", "image", "sbom", "provenance")):
        labels.append("supply-chain")
    if any(x in value for x in ("docs", "documentation", "readme")):
        labels.append("documentation")
    return tuple(labels)


def triage(gh: Gh) -> BotResult:
    changed = 0
    skipped = 0
    for item in gh.issues():
        number = item.get("number")
        if not isinstance(number, int):
            continue
        existing = {str(x.get("name", "")) for x in item.get("labels", []) if isinstance(x, Mapping)}
        for label in labels_for(f"{item.get('title', '')} {item.get('body', '')}"):
            if label not in existing:
                if gh.add_label(number, label):
                    changed += 1
                else:
                    skipped += 1
    return BotResult("issue-triage", changed, (f"classified open issues; {skipped} optional labels unavailable",))


def pr_triage(gh: Gh) -> BotResult:
    changed = 0
    skipped = 0
    for item in gh.prs():
        number = item.get("number")
        if not isinstance(number, int):
            continue
        existing = {str(x.get("name", "")) for x in item.get("labels", []) if isinstance(x, Mapping)}
        for label in labels_for(f"{item.get('title', '')} {item.get('body', '')}"):
            if label not in existing:
                if gh.add_label(number, label):
                    changed += 1
                else:
                    skipped += 1
    return BotResult("pr-triage", changed, (f"classified open PRs; {skipped} optional labels unavailable",))


def nightly_report(gh: Gh, results: Sequence[BotResult]) -> BotResult:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    issues = gh.issues()
    prs = gh.prs()
    security = [x for x in issues if "security" in {str(y.get("name", "")) for y in x.get("labels", []) if isinstance(y, Mapping)}]
    lines = [
        f"Night Shift report — {now}", "", f"Open issues: {len(issues)}", f"Open PRs: {len(prs)}",
        f"Security-labelled issues: {len(security)}", "", "Bots executed:",
        *[f"- {r.name}: {r.changed} changes — {'; '.join(r.notes) or 'ok'}" for r in results],
        "", "Safety: labels/issues only; no PR code execution, source mutation, security-gate weakening, or arbitrary merges.",
    ]
    title = "bot: night shift report"
    existing = gh.find_issue(title)
    body = "\n".join(lines)
    if existing is not None:
        number = int(existing["number"])
        gh.comment(number, body)
        gh.close_issue(number)
        return BotResult("nightly-report", 1, ("updated the closed report ledger",))
    created_number = gh.create_issue(title, body, ())
    gh.close_issue(created_number)
    return BotResult("nightly-report", 1, ("created and closed the report ledger",))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    args = parser.parse_args()
    if not args.repo:
        raise SystemExit("GITHUB_REPOSITORY is required")
    gh = Gh(args.repo)
    results = [triage(gh), pr_triage(gh)]
    nightly_report(gh, results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
