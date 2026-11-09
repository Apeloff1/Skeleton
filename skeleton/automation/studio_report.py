"""Human-readable reporting for autonomous studio audit logs."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import hashlib
from pathlib import Path
from typing import Iterable, Mapping, Sequence


MAX_AUDIT_BYTES = 10_000_000


def load_records(path: Path) -> tuple[dict[str, object], ...]:
    if path.is_symlink():
        raise ValueError("audit path symlink is forbidden")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError("audit path is unreadable") from exc
    if size > MAX_AUDIT_BYTES:
        raise ValueError("audit exceeds 10 MB safety bound")
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError("audit path is unreadable text") from exc
    records: list[dict[str, object]] = []
    for line_number, raw in enumerate(text.splitlines(), start=1):
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


def verify_audit_chain(records: Sequence[Mapping[str, object]]) -> None:
    previous = "0" * 64
    for index, row in enumerate(records, start=1):
        if row.get("sequence") != index:
            raise ValueError(f"audit sequence is discontinuous at record {index}")
        if row.get("previous_record_sha256") != previous:
            raise ValueError(f"audit hash chain is broken at record {index}")
        claimed = str(row.get("record_sha256", ""))
        payload = dict(row)
        payload.pop("record_sha256", None)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        if claimed != actual:
            raise ValueError(f"audit record hash mismatch at record {index}")
        previous = claimed


def render_report(records: Iterable[Mapping[str, object]]) -> str:
    rows = tuple(records)
    if not rows:
        return "# Autonomous Studio Report\n\nNo audit records were emitted."

    if all("record_sha256" in row for row in rows):
        verify_audit_chain(rows)
    events = Counter(str(row.get("event", "unknown")) for row in rows)
    first = rows[0]
    last = rows[-1]
    run_ids = {str(row.get("run_id", "")).strip() for row in rows if str(row.get("run_id", "")).strip()}
    if len(run_ids) > 1:
        raise ValueError("audit log contains records from multiple run ids")
    terminal_events = {"run_finished", "run_failed_closed", "run_blocked_by_operator", "shift_skipped_queue_pressure"}
    terminal = [row for row in rows if str(row.get("event", "")) in terminal_events]
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
        f"- Terminal controller records: **{len(terminal)}**",
        "",
        "## Controller integrity",
        "",
        (
            "- Audit lifecycle: **complete**"
            if len(terminal) == 1
            else f"- Audit lifecycle: **incomplete/ambiguous** ({len(terminal)} terminal records)"
        ),
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
