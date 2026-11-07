"""Markdown rendering for main-guard notices and reports.

Notices are intentionally short: who needs to act, on which commit, which job
failed at which step, and the exact next command.  They are plain markdown so
the same text works in a terminal, a commit comment, or a job summary.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from .gitops import CommitInfo
from .watcher import (
    ATTR_INHERITED,
    ATTR_INTRODUCED,
    ATTR_RANGE,
    ATTR_UNKNOWN,
    CommitReport,
    Failure,
    WatchReport,
)

MAX_SUSPECTS_SHOWN = 8

_ATTRIBUTION_LABEL = {
    ATTR_INTRODUCED: "introduced by this commit",
    ATTR_RANGE: "introduced in a multi-commit range",
    ATTR_INHERITED: "already red before this commit",
    ATTR_UNKNOWN: "no conclusive baseline found",
}

_VERDICT_ICON = {
    "red-new": "🔴",
    "red-inherited": "🟠",
    "red-unknown": "🟡",
    "pending": "⏳",
    "no-runs": "⚪",
    "green": "🟢",
}


def md_escape(text: str) -> str:
    """Escape characters that would change markdown table/inline rendering."""
    out = str(text).replace("\\", "\\\\")
    for ch in ("|", "`", "*", "_", "<", ">", "[", "]"):
        out = out.replace(ch, "\\" + ch)
    return out.replace("\n", " ").replace("\r", " ")


def author_label(commit: CommitInfo) -> str:
    name = md_escape(commit.author_name or "unknown")
    email = commit.author_email or ""
    if email.endswith("@users.noreply.github.com"):
        login = email.split("@", 1)[0].split("+", 1)[-1]
        return f"@{md_escape(login)} ({name})" if login and login != commit.author_name else f"@{name}"
    return f"{name} <{md_escape(email)}>" if email else name


def commit_line(commit: CommitInfo) -> str:
    return f"`{commit.short}` {md_escape(commit.subject)} — {author_label(commit)}"


def _link(label: str, url: str) -> str:
    return f"[{label}]({url})" if url else label


def _failure_row(failure: Failure) -> str:
    job = failure.job
    steps = ", ".join(md_escape(s) for s in job.failed_steps) or "—"
    focus = " ⚑" if failure.focus else ""
    return (
        f"| {md_escape(job.workflow)} | {_link(md_escape(job.job), job.url)}{focus} | {steps} | "
        f"{_ATTRIBUTION_LABEL.get(failure.attribution, failure.attribution)} |"
    )


def bisect_command(good: str, bad: str, test_cmd: str | None = None) -> str:
    cmd = test_cmd or "python3 -m pytest -q <failing test path>"
    return (
        f"python3 scripts/main_guard_bisect.py --good {good[:12]} --bad {bad[:12]} -- {cmd}"
    )


def suggested_test_command(failure: Failure) -> str | None:
    job = failure.job.job
    if job == "Backend Test":
        return "bash -c 'cd backend && python3 -m pytest -q tests -m \"not live_service\"'"
    if job == "Skeleton GameForge":
        return "python3 tests/run_unit.py"
    return None


def render_commit_notice(commit: CommitReport, report: WatchReport | None = None) -> str:
    """Render the fix-forward notice for one commit."""
    c = commit.commit
    icon = _VERDICT_ICON.get(commit.verdict, "")
    lines: list[str] = [f"### {icon} main-guard: fix-forward notice for `{c.short}`".replace("  ", " "), ""]
    lines.append(f"**Commit:** {commit_line(c)}")
    if report is not None:
        lines.append(f"**Branch:** `{md_escape(report.branch)}` in `{md_escape(report.repo)}`")
    lines.append("")
    if not commit.failures:
        if commit.pending:
            lines.append("Watched workflows are still running; no failures yet.")
        elif not commit.runs:
            lines.append("No watched push workflows were found for this commit.")
        else:
            lines.append("All watched jobs passed. Nothing to fix.")
        return "\n".join(lines).rstrip() + "\n"

    lines.append("| Workflow | Job | Failed step(s) | Attribution |")
    lines.append("|---|---|---|---|")
    lines.extend(_failure_row(f) for f in commit.failures)
    lines.append("")

    new = commit.new_failures
    if new:
        lines.append("**Action (fix forward, do not revert other agents' work):**")
        for failure in new:
            lines.extend(_action_lines(commit, failure))
        lines.append("")
    inherited = commit.inherited_failures
    if inherited:
        base = inherited[0].baseline_sha or ""
        names = ", ".join(sorted({md_escape(f.job.job) for f in inherited}))
        lines.append(
            f"Inherited reds ({names}) were already failing at `{base[:8]}`; they are owned by earlier "
            "commits and are not attributed to this push."
        )
        lines.append("")
    unknown = [f for f in commit.failures if f.attribution == ATTR_UNKNOWN]
    if unknown:
        names = ", ".join(sorted({md_escape(f.job.job) for f in unknown}))
        lines.append(
            f"No conclusive earlier result for {names}; treat as possibly introduced and verify locally."
        )
        lines.append("")
    if commit.missing_workflows:
        lines.append("Missing watched workflows: " + ", ".join(md_escape(w) for w in commit.missing_workflows))
        lines.append("")
    lines.append("_Generated by `scripts/main_guard_watch.py` (dry-run unless `--post`)._")
    return "\n".join(lines).rstrip() + "\n"


def _action_lines(commit: CommitReport, failure: Failure) -> list[str]:
    job = failure.job
    out: list[str] = []
    if failure.attribution == ATTR_INTRODUCED:
        out.append(
            f"- {author_label(commit.commit)}: `{md_escape(job.job)}` went red with this commit "
            f"(green at `{(failure.baseline_sha or '')[:8]}`). Push a fix-forward commit to `main`."
        )
        return out
    suspects = failure.suspects
    shown = suspects[-MAX_SUSPECTS_SHOWN:]
    authors = sorted({author_label(s) for s in suspects})
    out.append(
        f"- `{md_escape(job.job)}` went red somewhere in {len(suspects)} commits after green "
        f"`{(failure.baseline_sha or '')[:8]}` (authors: {', '.join(authors)}):"
    )
    if len(suspects) > len(shown):
        out.append(f"  - … {len(suspects) - len(shown)} older suspect(s) omitted")
    out.extend(f"  - {commit_line(s)}" for s in shown)
    if failure.baseline_sha:
        out.append(
            "  - Find the first bad commit: `"
            + bisect_command(failure.baseline_sha, commit.commit.sha, suggested_test_command(failure))
            + "`"
        )
    return out


def render_watch_report(report: WatchReport) -> str:
    lines = [
        f"## main-guard post-push report — `{md_escape(report.repo)}@{md_escape(report.branch)}`",
        "",
        "| Commit | Author | Verdict | New | Inherited |",
        "|---|---|---|---|---|",
    ]
    for commit in report.commits:
        c = commit.commit
        icon = _VERDICT_ICON.get(commit.verdict, "")
        lines.append(
            f"| `{c.short}` {md_escape(c.subject[:60])} | {author_label(c)} | {icon} {commit.verdict} | "
            f"{len(commit.new_failures)} | {len(commit.inherited_failures)} |"
        )
    lines.append("")
    red = [c for c in report.commits if c.failures]
    for commit in red:
        lines.append(render_commit_notice(commit, report))
    if not red:
        lines.append("No failing watched jobs in the selected commits.")
    return "\n".join(lines).rstrip() + "\n"


def render_bullets(items: Iterable[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def render_table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    head = "| " + " | ".join(md_escape(h) for h in headers) + " |"
    sep = "|" + "|".join("---" for _ in headers) + "|"
    body = ["| " + " | ".join(md_escape(str(cell)) for cell in row) + " |" for row in rows]
    return "\n".join([head, sep, *body])
