#!/usr/bin/env python3
"""Read-only inventory of GitHub Actions schedule pressure.

This is a lexical inventory, not a full YAML interpreter, live Actions meter,
security gate, or deletion authority. Unsupported cron expressions stay unknown.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

MAX_FILES = 2000
MAX_BYTES = 256 * 1024
_TOP = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*\s*:")
_SECTION = re.compile(r"^  ([A-Za-z_][A-Za-z0-9_-]*):")
_CRON = re.compile(r"^\s*-\s*cron:\s*(.+?)\s*$")


def workflow_crons(source: str) -> list[str]:
    """Extract block-form on.schedule entries without interpreting run scripts."""
    if not isinstance(source, str):
        raise ValueError("workflow text required")
    rows = source.splitlines()
    start = next((i for i, row in enumerate(rows) if row.strip() == "on:" and row == "on:"), None)
    if start is None:
        return []
    crons: list[str] = []
    within_schedule = False
    for line in rows[start + 1:]:
        if line and not line[0].isspace() and _TOP.match(line):
            break
        section = _SECTION.match(line)
        if section:
            within_schedule = section.group(1) == "schedule"
        if not within_schedule:
            continue
        match = _CRON.match(line)
        if match:
            raw = match.group(1).split("#", 1)[0].strip()
            if len(raw) >= 2 and raw[0] in "'\"" and raw[-1] == raw[0]:
                raw = raw[1:-1]
            crons.append(raw)
    return crons


def _fields(text: str, lower: int, upper: int) -> set[int] | None:
    if not text or len(text) > 128:
        return None
    result: set[int] = set()
    for atom in text.split(","):
        expression, sep, step_text = atom.partition("/")
        if sep:
            if not step_text.isdecimal() or not 1 <= int(step_text) <= upper + 1:
                return None
            step = int(step_text)
        else:
            step = 1
        if expression == "*":
            left, right = lower, upper
        elif "-" in expression:
            left_text, separator, right_text = expression.partition("-")
            if not separator or not left_text.isdecimal() or not right_text.isdecimal():
                return None
            left, right = int(left_text), int(right_text)
        elif expression.isdecimal():
            left = int(expression)
            right = upper if sep else left
        else:
            return None
        if not lower <= left <= right <= upper:
            return None
        result.update(range(left, right + 1, step))
    return result if result else None


def nominal_daily_wakes(expression: str) -> int | None:
    """Count only explicit daily schedules in UTC. Never extrapolate special dates."""
    parts = expression.split()
    if len(parts) != 5:
        return None
    minute, hour, day, month, weekday = parts
    # Month/day/week filters and aliases are not safely comparable as daily rates.
    if (day, month, weekday) != ("*", "*", "*"):
        return None
    minutes = _fields(minute, 0, 59)
    hours = _fields(hour, 0, 23)
    if minutes is None or hours is None:
        return None
    return len(minutes) * len(hours)


def inventory(root: Path) -> dict[str, object]:
    """Inventory tracked worktree definitions, not historical Actions executions."""
    folder = root / ".github" / "workflows"
    if not folder.is_dir() or folder.is_symlink():
        raise ValueError("workflow directory missing or unsafe")
    paths = sorted(p for p in folder.iterdir()
                   if p.suffix in {".yml", ".yaml"} and p.is_file() and not p.is_symlink())
    if not paths or len(paths) > MAX_FILES:
        raise ValueError("workflow inventory missing or exceeds file budget")
    records: list[dict[str, object]] = []
    for path in paths:
        if path.stat().st_size > MAX_BYTES:
            records.append({"path": path.name, "crons": [], "daily_wakes": None,
                            "note": "definition exceeds safe read budget"})
            continue
        try:
            crons = workflow_crons(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            records.append({"path": path.name, "crons": [], "daily_wakes": None,
                            "note": "definition unreadable"})
            continue
        estimates = [nominal_daily_wakes(expr) for expr in crons]
        daily = sum(estimates) if all(x is not None for x in estimates) else None
        records.append({
            "path": path.name, "crons": crons, "daily_wakes": daily,
            "note": "unknown cron semantics" if daily is None else (
                "high-frequency recurring wake" if daily >= 96 else ""
            ),
        })
    scheduled = [r for r in records if r["crons"]]
    unknown = [r for r in records if r["daily_wakes"] is None]
    return {
        "schema_version": 1,
        "scope": "worktree-schedule-config-only",
        "workflow_files": len(records),
        "scheduled_workflows": len(scheduled),
        "unknown_or_unreadable": len(unknown),
        "known_nominal_daily_wakes": sum(r["daily_wakes"] for r in records
                                         if r["daily_wakes"] is not None),
        "caveat": "Does not count PR/push dispatch, matrix jobs, runner queue or actual completed runs",
        "workflows": records,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--top", type=int, default=25)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.top <= MAX_FILES:
        parser.error("--top must be in [1,2000]")
    try:
        report = inventory(args.root)
    except (ValueError, OSError) as exc:
        parser.exit(2, f"workflow inventory failed closed: {exc}\n")
    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2))
    else:
        print("Workflow files:", report["workflow_files"])
        print("Scheduled workflows:", report["scheduled_workflows"])
        print("Nominal known daily wakes:", report["known_nominal_daily_wakes"])
        print("Unknown/unsupported definitions:", report["unknown_or_unreadable"])
        print("Known high-frequency workflows:")
        ranked = sorted(report["workflows"], key=lambda r: (
            -(r["daily_wakes"] if r["daily_wakes"] is not None else -1),
            r["path"],
        ))
        for entry in ranked[:args.top]:
            print(f"  {entry['path']}: {entry['daily_wakes']} configured daily wakes")
        print("The count is only configuration, not Actions execution telemetry.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
