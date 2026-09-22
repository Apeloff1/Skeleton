from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

_NORMAL_SHIFT_MINUTES = 8 * 60
_SQUAD_ROLE_FIELDS = (
    ("researcher", "researcher"),
    ("builder", "builder"),
    ("reviewer", "reviewer"),
    ("verifier", "verifier"),
)


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _audit_rows(path: Path) -> list[Mapping[str, Any]]:
    if not path.is_file():
        return []
    rows: list[Mapping[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[:500]:
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, Mapping):
            rows.append(value)
    return rows


def _elapsed_minutes(
    rows: Iterable[Mapping[str, Any]],
    *,
    ended_at: datetime | None = None,
) -> tuple[str, str, int]:
    """Return the bounded run envelope represented by the audit itself.

    Do not extend a historical audit to wall-clock ``now``. Workforce reports
    can be regenerated later, and doing so must not manufacture overtime.
    """
    timestamps = [stamp for row in rows if (stamp := _parse_time(row.get("ts"))) is not None]
    now = ended_at or datetime.now(timezone.utc)
    started = min(timestamps) if timestamps else now
    if ended_at is not None:
        ended = max([*timestamps, ended_at]) if timestamps else ended_at
    else:
        ended = max(timestamps) if timestamps else now
    elapsed = max(1, math.ceil((ended - started).total_seconds() / 60))
    return started.isoformat(), ended.isoformat(), elapsed


def _worker_payload(
    *,
    worker_id: str,
    team: str,
    tasks: Sequence[str],
    roles: Sequence[str],
    started_at: str,
    ended_at: str,
    elapsed_minutes: int,
) -> dict[str, Any]:
    unique_tasks = list(dict.fromkeys(task for task in tasks if task))[:64]
    normal = min(elapsed_minutes, _NORMAL_SHIFT_MINUTES)
    overtime = max(0, elapsed_minutes - _NORMAL_SHIFT_MINUTES)
    shift_key = f"{team}:{worker_id}:{started_at}:{ended_at}"
    return {
        "worker_id": worker_id,
        "team": team,
        "status": "offline",
        "clocked_in_at": started_at,
        "clocked_out_at": ended_at,
        "last_heartbeat_at": ended_at,
        "current_task_id": None,
        "normal_shift_minutes": normal,
        "overtime_minutes": overtime,
        "overtime_task_ids": unique_tasks if overtime else [],
        "metadata": {
            "worked_on": unique_tasks,
            "roles": list(dict.fromkeys(role for role in roles if role))[:16],
            "last_task_id": unique_tasks[-1] if unique_tasks else None,
            "shift_key": shift_key,
            "shift_minutes": elapsed_minutes,
            "shift_started_at": started_at,
            "shift_ended_at": ended_at,
            "time_basis": "run-envelope",
        },
    }


def idle_snapshot(package_path: Path, audit_path: Path) -> dict[str, Any]:
    package = json.loads(package_path.read_text(encoding="utf-8")) if package_path.is_file() else {}
    entries = package.get("entries", []) if isinstance(package, Mapping) else []
    rows = _audit_rows(audit_path)
    started_at, ended_at, elapsed = _elapsed_minutes(rows)
    workers: dict[str, dict[str, list[str]]] = {}

    if isinstance(entries, list):
        for entry in entries[:100]:
            if not isinstance(entry, Mapping):
                continue
            task = entry.get("task", {})
            task_id = str(task.get("key", "")) if isinstance(task, Mapping) else ""
            for field, role in _SQUAD_ROLE_FIELDS:
                raw = entry.get(field, {})
                if not isinstance(raw, Mapping):
                    continue
                worker_id = str(raw.get("worker_id", "")).strip()
                if not worker_id:
                    continue
                record = workers.setdefault(worker_id, {"tasks": [], "roles": []})
                record["tasks"].append(task_id)
                record["roles"].append(str(raw.get("role", role)) or role)

    return {
        "version": 1,
        "team": "idle",
        "updated_at": ended_at,
        "workers": [
            _worker_payload(
                worker_id=worker_id,
                team="idle",
                tasks=record["tasks"],
                roles=record["roles"],
                started_at=started_at,
                ended_at=ended_at,
                elapsed_minutes=elapsed,
            )
            for worker_id, record in sorted(workers.items())
        ],
    }


def night_snapshot(audit_path: Path) -> dict[str, Any]:
    rows = _audit_rows(audit_path)
    started_at, ended_at, elapsed = _elapsed_minutes(rows)
    workers: dict[str, dict[str, list[str]]] = {}

    for row in rows:
        if row.get("event") != "patch_accepted":
            continue
        task_id = str(row.get("task", "")).strip()
        for field, role in _SQUAD_ROLE_FIELDS:
            worker_id = str(row.get(field, "")).strip()
            if not worker_id:
                continue
            record = workers.setdefault(worker_id, {"tasks": [], "roles": []})
            record["tasks"].append(task_id)
            record["roles"].append(role)

    return {
        "version": 1,
        "team": "night",
        "updated_at": ended_at,
        "workers": [
            _worker_payload(
                worker_id=worker_id,
                team="night",
                tasks=record["tasks"],
                roles=record["roles"],
                started_at=started_at,
                ended_at=ended_at,
                elapsed_minutes=elapsed,
            )
            for worker_id, record in sorted(workers.items())
        ],
    }


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Derive SMB workforce snapshots from studio evidence")
    sub = parser.add_subparsers(dest="command", required=True)
    idle = sub.add_parser("idle")
    idle.add_argument("--package", required=True)
    idle.add_argument("--audit", required=True)
    idle.add_argument("--output", required=True)
    night = sub.add_parser("night")
    night.add_argument("--audit", required=True)
    night.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    output = Path(args.output)
    if args.command == "idle":
        _write(output, idle_snapshot(Path(args.package), Path(args.audit)))
    else:
        _write(output, night_snapshot(Path(args.audit)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())