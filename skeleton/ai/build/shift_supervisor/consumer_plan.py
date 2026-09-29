from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

PLAN_TITLE = "[Shift Supervisor] Canonical Night + Idle Plan"
STATUS_TITLES = {
    "[Shift Supervisor] Idle Worker Status",
    "[Shift Supervisor] Night Worker Status",
}
_STATE_PATTERN = re.compile(r"<!-- SHIFT_SUPERVISOR_STATE\n(.*?)\n-->", re.DOTALL)
_ACTIVE_RUN_STATES = {"queued", "in_progress", "waiting", "pending"}


class CanonicalPlanError(RuntimeError):
    """Raised when a studio cannot safely consume the canonical supervisor plan."""


def _parse_time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def decode_durable_state(body: str) -> Mapping[str, Any]:
    match = _STATE_PATTERN.search(body)
    if not match:
        raise CanonicalPlanError("canonical plan issue has no durable machine state")
    encoded = match.group(1).strip()
    if not encoded.startswith("gz:v1:"):
        raise CanonicalPlanError("canonical plan state encoding is unsupported")
    try:
        packed = base64.b64decode(encoded[len("gz:v1:") :], validate=True)
        value = json.loads(gzip.decompress(packed).decode("utf-8"))
    except (ValueError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CanonicalPlanError("canonical plan machine state is corrupt") from exc
    if not isinstance(value, Mapping) or value.get("version") != 1:
        raise CanonicalPlanError("canonical plan state version is unsupported")
    plan_items = value.get("plan_items")
    if not isinstance(plan_items, list):
        raise CanonicalPlanError("canonical plan state has no plan_items list")
    return value


def _issue_rows(state: Mapping[str, Any]) -> tuple[str, list[Mapping[str, Any]]]:
    for key in ("open_issues", "issues"):
        raw = state.get(key)
        if isinstance(raw, list):
            return key, [item for item in raw if isinstance(item, Mapping)]
    raise CanonicalPlanError("repository snapshot has no issue collection")


def _canonical_issue(state: Mapping[str, Any]) -> tuple[str, Mapping[str, Any], list[Mapping[str, Any]]]:
    issue_key, issues = _issue_rows(state)
    canonical = next((item for item in issues if str(item.get("title", "")) == PLAN_TITLE), None)
    if canonical is None:
        raise CanonicalPlanError("canonical supervisor plan issue is missing")
    return issue_key, canonical, issues


def _executable_team_items(raw_plan: object, team: str) -> list[dict[str, Any]]:
    if not isinstance(raw_plan, list):
        raise CanonicalPlanError("canonical plan state has no plan_items list")
    rows = [item for item in raw_plan if isinstance(item, Mapping)]
    by_id = {
        str(item.get("id", "")).strip(): item
        for item in rows
        if str(item.get("id", "")).strip()
    }
    executable: list[dict[str, Any]] = []
    for item in rows:
        if item.get("target_team") != team or str(item.get("status", "queued")).lower() != "queued":
            continue
        item_id = str(item.get("id", "")).strip()
        title = str(item.get("title", "")).strip()
        description = str(item.get("description", "")).strip()
        if not item_id or not title or not description:
            continue
        dependencies = item.get("dependencies", [])
        if not isinstance(dependencies, list):
            continue
        dependency_ids = [str(value).strip() for value in dependencies if str(value).strip()]
        if any(
            dependency_id not in by_id
            or str(by_id[dependency_id].get("status", "")).lower() != "done"
            for dependency_id in dependency_ids
        ):
            continue
        executable.append(dict(item))
    return executable


def consume_plan(
    state: dict[str, Any],
    *,
    team: str,
    now: datetime | None = None,
    max_age_minutes: int = 20,
) -> tuple[dict[str, Any], dict[str, str]]:
    if team not in {"night", "idle"}:
        raise ValueError("team must be night or idle")
    if max_age_minutes < 1:
        raise ValueError("max_age_minutes must be positive")

    issue_key, canonical, issues = _canonical_issue(state)
    updated = _parse_time(canonical.get("updatedAt") or canonical.get("updated_at"))
    if updated is None:
        raise CanonicalPlanError("canonical supervisor plan has no parseable updated timestamp")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age = current - updated
    if age < timedelta(minutes=-2):
        raise CanonicalPlanError("canonical supervisor plan timestamp is unexpectedly in the future")
    if age > timedelta(minutes=max_age_minutes):
        raise CanonicalPlanError(
            f"canonical supervisor plan is stale ({int(age.total_seconds() // 60)} minutes old)"
        )

    durable = decode_durable_state(str(canonical.get("body", "")))
    team_items = _executable_team_items(durable.get("plan_items", []), team)
    if not team_items:
        raise CanonicalPlanError(f"canonical supervisor plan has no executable {team} items")

    issue_number = canonical.get("number")
    generation_seed = json.dumps(
        {
            "issue": issue_number,
            "updated": updated.isoformat(),
            "plan_ids": [str(item.get("id")) for item in team_items],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    generation_id = hashlib.sha256(generation_seed.encode("utf-8")).hexdigest()[:20]
    state["_shift_supervisor"] = {
        "source": "canonical-plan-issue",
        "status": "loaded",
        "generation_id": generation_id,
        "issue_number": issue_number,
        "updated_at": updated.isoformat(),
        "max_age_minutes": max_age_minutes,
        "team": team,
        "plan_items": team_items[:32],
    }

    state[issue_key] = [
        dict(item)
        for item in issues
        if str(item.get("title", "")) not in ({PLAN_TITLE} | STATUS_TITLES)
    ]

    plan_map: dict[str, str] = {}
    if team == "idle":
        synthetic: list[dict[str, Any]] = []
        for item in team_items[:32]:
            plan_id = str(item["id"])
            stable = hashlib.sha256(plan_id.encode("utf-8")).hexdigest()
            number = -(int(stable[:12], 16) + 1)
            priority = item.get("priority", 50)
            try:
                priority = max(1, min(100, int(priority)))
            except (TypeError, ValueError):
                priority = 50
            title = str(item.get("title", "")).strip()
            evidence = {
                "source": "canonical-shift-supervisor",
                "plan_item_id": plan_id,
                "generation_id": generation_id,
                "priority": priority,
                "description": str(item.get("description", "")),
                "rationale": str(item.get("rationale", "")),
                "expected_output": str(item.get("expected_output", "")),
                "validation": item.get("validation", []),
                "dependencies": item.get("dependencies", []),
                "research_refs": item.get("research_refs", []),
            }
            labels = [{"name": "shift-supervisor"}]
            text = f"{title} {evidence['description']}".lower()
            if any(token in text for token in ("security", "vulnerability", "cve", "secret", "auth")):
                labels.append({"name": "security"})
            synthetic.append(
                {
                    "number": number,
                    "title": f"[Supervisor {plan_id} P{priority}] {title}"[:300],
                    "body": json.dumps(evidence, sort_keys=True, default=str)[:12000],
                    "labels": labels,
                }
            )
            plan_map[f"issue:{number}"] = plan_id

        state[issue_key] = synthetic
        runs = state.get("runs", [])
        if isinstance(runs, list):
            state["runs"] = [
                item
                for item in runs
                if isinstance(item, Mapping)
                and str(item.get("status", "")).lower() in _ACTIVE_RUN_STATES
            ]
        # Fresh pull state is re-read by the publisher before any mutation. Do
        # not let open PR review suggestions become independent work producers.
        state["pulls"] = []

    return state, plan_map


def _summary(team: str, state: Mapping[str, Any], *, error: str | None = None) -> str:
    lines = ["## Shift supervisor", ""]
    if error:
        lines += ["Status: **blocked**", "", error, "", "No studio work was generated."]
        return "\n".join(lines) + "\n"
    supervisor = state.get("_shift_supervisor", {})
    items = supervisor.get("plan_items", []) if isinstance(supervisor, Mapping) else []
    lines += [
        "Status: **canonical plan loaded**",
        "",
        f"Generation: `{supervisor.get('generation_id', '')}`",
        f"Updated: `{supervisor.get('updated_at', '')}`",
        f"{team.title()} plan items available: **{len(items) if isinstance(items, list) else 0}**",
    ]
    return "\n".join(lines) + "\n"


def prepare_state(
    state_path: Path,
    *,
    team: str,
    summary_path: Path,
    plan_map_path: Path | None = None,
    max_age_minutes: int = 20,
    now: datetime | None = None,
) -> None:
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise CanonicalPlanError("repository snapshot must be a JSON object")
        state, plan_map = consume_plan(
            raw,
            team=team,
            now=now,
            max_age_minutes=max_age_minutes,
        )
    except (OSError, json.JSONDecodeError, CanonicalPlanError) as exc:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(_summary(team, {}, error=str(exc)), encoding="utf-8")
        raise CanonicalPlanError(str(exc)) from exc

    state_path.write_text(json.dumps(state, sort_keys=True, indent=2), encoding="utf-8")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(_summary(team, state), encoding="utf-8")
    if plan_map_path is not None:
        plan_map_path.parent.mkdir(parents=True, exist_ok=True)
        plan_map_path.write_text(json.dumps(plan_map, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def normalize_worker_status(status_path: Path, plan_map_path: Path) -> None:
    if not status_path.is_file() or not plan_map_path.is_file():
        return
    status = json.loads(status_path.read_text(encoding="utf-8"))
    mapping = json.loads(plan_map_path.read_text(encoding="utf-8"))
    if not isinstance(status, dict) or not isinstance(mapping, dict):
        return
    workers = status.get("workers", [])
    if not isinstance(workers, list):
        return
    for worker in workers:
        if not isinstance(worker, dict):
            continue
        metadata = worker.get("metadata")
        if not isinstance(metadata, dict):
            continue
        worked_on = metadata.get("worked_on", [])
        if isinstance(worked_on, list):
            metadata["worked_on"] = [mapping.get(str(item), str(item)) for item in worked_on]
        last_task = metadata.get("last_task_id")
        if last_task is not None:
            metadata["last_task_id"] = mapping.get(str(last_task), str(last_task))
        overtime = worker.get("overtime_task_ids", [])
        if isinstance(overtime, list):
            worker["overtime_task_ids"] = [mapping.get(str(item), str(item)) for item in overtime]
    status_path.write_text(json.dumps(status, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _parse_now(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = _parse_time(value)
    if parsed is None:
        raise ValueError("--now must be an ISO-8601 timestamp")
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Fail-closed studio consumer for the canonical shift-supervisor plan")
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--team", choices=("night", "idle"), required=True)
    prepare.add_argument("--state", required=True)
    prepare.add_argument("--summary", required=True)
    prepare.add_argument("--plan-map")
    prepare.add_argument("--max-age-minutes", type=int, default=20)
    prepare.add_argument("--now")
    normalize = sub.add_parser("normalize-worker-status")
    normalize.add_argument("--status", required=True)
    normalize.add_argument("--plan-map", required=True)
    args = parser.parse_args(argv)

    if args.command == "normalize-worker-status":
        normalize_worker_status(Path(args.status), Path(args.plan_map))
        return 0
    try:
        prepare_state(
            Path(args.state),
            team=args.team,
            summary_path=Path(args.summary),
            plan_map_path=Path(args.plan_map) if args.plan_map else None,
            max_age_minutes=args.max_age_minutes,
            now=_parse_now(args.now),
        )
    except CanonicalPlanError as exc:
        print(f"canonical plan rejected: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
