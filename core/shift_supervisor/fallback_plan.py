from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

PLAN_TITLE = "[Shift Supervisor] Canonical Night + Idle Plan"
_STATUS_PREFIX = "[Shift Supervisor]"
_ALLOWED_TEAMS = ("night", "idle")
_BOOTSTRAP_ISSUES = frozenset({1685})
_APPROVAL_LABELS = frozenset({"supervisor-ready", "build-approved", "security-approved"})


def _priority(issue: Mapping[str, Any]) -> int:
    labels = {
        str(item.get("name", item)).lower()
        for item in issue.get("labels", [])
        if isinstance(item, (str, Mapping))
    }
    if labels & {"security", "critical", "p0"}:
        return 100
    if labels & {"bug", "ci", "p1"}:
        return 90
    return 70


def _eligible(issue: Mapping[str, Any]) -> bool:
    title = str(issue.get("title", "")).strip()
    number = issue.get("number")
    labels = {
        str(item.get("name", item)).lower()
        for item in issue.get("labels", [])
        if isinstance(item, (str, Mapping))
    }
    try:
        issue_number = int(number)
    except (TypeError, ValueError):
        return False
    authorized = issue_number in _BOOTSTRAP_ISSUES or bool(labels & _APPROVAL_LABELS)
    return bool(title and authorized and not title.startswith(_STATUS_PREFIX))


def compile_fallback_state(context: Mapping[str, Any], previous: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Compile a deterministic, bounded plan when advisory model planning is unavailable.

    The fallback never invents repository work. It selects only open issues already
    present in the trusted snapshot, preserving Supervisor->Secretary->Worker custody.
    """
    issues = context.get("open_issues", context.get("issues", []))
    if not isinstance(issues, list):
        issues = []
    candidates = [item for item in issues if isinstance(item, Mapping) and _eligible(item)]
    candidates.sort(key=lambda item: (-_priority(item), int(item.get("number", 0))))

    prior_items = []
    if isinstance(previous, Mapping) and isinstance(previous.get("plan_items"), list):
        prior_items = [
            dict(item) for item in previous["plan_items"]
            if isinstance(item, Mapping)
            and str(item.get("status", "queued")).lower() in {"queued", "assigned", "blocked"}
        ][:16]

    seen = {str(item.get("id", "")) for item in prior_items}
    generated: list[dict[str, Any]] = []
    for index, issue in enumerate(candidates[:16]):
        number = int(issue["number"])
        item_id = f"issue-{number}"
        if item_id in seen:
            continue
        title = str(issue["title"]).strip()
        body = str(issue.get("body", "")).strip()
        team = _ALLOWED_TEAMS[index % len(_ALLOWED_TEAMS)]
        generated.append({
            "id": item_id,
            "title": title[:300],
            "description": (body[:1200] or f"Advance repository issue #{number} within its stated acceptance criteria."),
            "priority": _priority(issue),
            "target_team": team,
            "status": "queued",
            "owner": None,
            "dependencies": [],
            "validation": ["focused regression tests", "required repository CI"],
            "expected_output": f"Validated focused PR advancing issue #{number}",
            "source_issue": number,
            "planner": "deterministic-failover-v1",
        })

    plan_items = (prior_items + generated)[:24]
    if not plan_items:
        raise RuntimeError("deterministic supervisor failover found no authorized open issue work")

    fingerprint_payload = json.dumps(
        [{"id": item["id"], "status": item.get("status")} for item in plan_items],
        sort_keys=True,
        separators=(",", ":"),
    )
    return {
        "version": 1,
        "plan_items": plan_items,
        "workers": list(previous.get("workers", []))[:96] if isinstance(previous, Mapping) else [],
        "revisions": [{
            "actor": "supervisor-failover",
            "summary": "Advisory model planning unavailable; deterministic issue-backed plan compiled.",
            "at": datetime.now(timezone.utc).isoformat(),
        }],
        "planner_mode": "deterministic_failover",
        "plan_fingerprint": hashlib.sha256(fingerprint_payload.encode()).hexdigest(),
    }


def emit_failover_outputs(context_path: str, previous: Mapping[str, Any] | None, result_path: str, state_path: str) -> dict[str, Any]:
    from .__main__ import _write_state

    context = json.loads(Path(context_path).read_text(encoding="utf-8"))
    state = compile_fallback_state(context, previous)
    result = {
        "actors": ["supervisor-failover"],
        "plan_items": state["plan_items"],
        "workers": state["workers"],
        "revisions": {"supervisor-failover": {"summary": "Deterministic issue-backed failover plan; advisory model unavailable."}},
        "planner_mode": state["planner_mode"],
        "plan_fingerprint": state["plan_fingerprint"],
    }
    Path(result_path).write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    _write_state(Path(state_path), state)
    return result


def main(context_path: str, state_path: str, output_path: str) -> None:
    context = json.loads(Path(context_path).read_text(encoding="utf-8"))
    previous: dict[str, Any] = {}
    state_file = Path(state_path)
    if state_file.is_file() and state_file.read_text(encoding="utf-8").strip().startswith("{"):
        previous = json.loads(state_file.read_text(encoding="utf-8"))
    result = compile_fallback_state(context, previous)
    Path(output_path).write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
