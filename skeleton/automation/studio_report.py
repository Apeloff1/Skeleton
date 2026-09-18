"""Human-readable reporting for autonomous studio audit logs."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence


def load_records(path: Path) -> tuple[dict[str, object], ...]:
    records: list[dict[str, object]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at line {line_number}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"audit line {line_number} must be an object")
        records.append(value)
    return tuple(records)


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def render_report(records: Iterable[Mapping[str, object]]) -> str:
    rows = tuple(records)
    if not rows:
        return "# Autonomous Studio Report\n\nNo audit records were emitted."

    events = Counter(str(row.get("event", "unknown")) for row in rows)
    first = rows[0]
    last = rows[-1]
    cohort = _as_list(first.get("cohort"))
    plan_rows = [
        task
        for row in rows
        if row.get("event") == "plan_created"
        for task in _as_list(row.get("tasks"))
        if isinstance(task, dict)
    ]
    accepted = [row for row in rows if row.get("event") == "patch_accepted"]
    rejected = [
        row
        for row in rows
        if str(row.get("event", "")).startswith("patch_rejected")
        or row.get("event") in {"task_failed_closed", "run_failed_closed"}
    ]

    lines = [
        "# Autonomous Studio Report",
        "",
        f"- Run: `{first.get('run_id', 'unknown')}`",
        f"- Started: `{first.get('ts', 'unknown')}`",
        f"- Finished: `{last.get('ts', 'unknown')}`",
        f"- Registered virtual workers: **{first.get('studio_size', 'unknown')}**",
        f"- Active bounded cohort: **{len(cohort)}**",
        f"- Planned tasks: **{len(plan_rows)}**",
        f"- Accepted patches: **{len(accepted)}**",
        f"- Rejected/failed-closed tasks or runs: **{len(rejected)}**",
        "",
        "## Planned work",
        "",
    ]
    if not plan_rows:
        lines.append("- No tasks were planned.")
    else:
        for task in plan_rows:
            paths = ", ".join(str(path) for path in _as_list(task.get("paths")))
            lines.append(
                f"- **{task.get('title', 'untitled')}** "
                f"({task.get('division', 'unknown')}): {task.get('objective', '')}"
            )
            if paths:
                lines.append(f"  - Scope: `{paths}`")

    lines.extend(["", "## Accepted work", ""])
    if not accepted:
        lines.append("- No model proposal cleared deterministic policy + senior review in this run.")
    else:
        for row in accepted:
            lines.append(
                f"- **{row.get('task', 'untitled')}** — builder `{row.get('builder', '?')}`, "
                f"reviewer `{row.get('reviewer', '?')}`"
            )
            if row.get("summary"):
                lines.append(f"  - {row['summary']}")
            reasons = row.get("review_reasons")
            if isinstance(reasons, list) and reasons:
                lines.append("  - Review evidence: " + "; ".join(str(reason) for reason in reasons))

    lines.extend(["", "## Fail-closed / rejected work", ""])
    if not rejected:
        lines.append("- None.")
    else:
        for row in rejected:
            detail = row.get("reason") or row.get("error") or row.get("event")
            subject = row.get("task") or row.get("stage") or "run"
            lines.append(f"- **{subject}**: {detail}")

    lines.extend(
        [
            "",
            "## Audit event counts",
            "",
            *[f"- `{event}`: {count}" for event, count in sorted(events.items())],
            "",
            "## Safety boundary",
            "",
            "Model output is treated as an untrusted patch proposal. The director rejects high-risk paths, "
            "renames/deletions, scope escape, malformed diffs, and oversized work. Generated code is validated "
            "without the OpenAI API key in its environment. Repository publication happens only after validation "
            "and always through a reviewable branch/PR, never by direct write to `main`.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    report = render_report(load_records(Path(args.audit)))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
