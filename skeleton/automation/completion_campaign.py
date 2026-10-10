from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .shift_supervisor.consumer_plan import canonical_queue_drained

SCHEMA = "autonomous-studio.completion-campaign.v1"
TERMINAL_STATES = {"complete", "quarantined", "exhausted"}
MAX_HISTORY = 64


@dataclass
class CampaignPolicy:
    max_cycles: int = 40
    max_stagnant_cycles: int = 3
    max_failures: int = 5
    max_task_attempts: int = 4

    def validate(self) -> None:
        if not 1 <= self.max_cycles <= 200:
            raise ValueError("max_cycles must be between 1 and 200")
        if not 1 <= self.max_stagnant_cycles <= 20:
            raise ValueError("max_stagnant_cycles must be between 1 and 20")
        if not 1 <= self.max_failures <= 50:
            raise ValueError("max_failures must be between 1 and 50")
        if not 1 <= self.max_task_attempts <= 20:
            raise ValueError("max_task_attempts must be between 1 and 20")


@dataclass
class CampaignState:
    schema: str = SCHEMA
    campaign_id: str = ""
    status: str = "active"
    cycle: int = 0
    failures: int = 0
    stagnant_cycles: int = 0
    last_progress_fingerprint: str = ""
    last_generation_id: str = ""
    task_attempts: dict[str, int] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    terminal_reason: str = ""
    epoch: int = 0
    state_sha256: str = ""
    lease_owner: str = ""
    lease_epoch: int = 0
    task_cooldowns: dict[str, int] = field(default_factory=dict)
    lane_health: dict[str, dict[str, Any]] = field(default_factory=dict)
    task_age: dict[str, int] = field(default_factory=dict)
    last_allocation_sha256: str = ""

    @classmethod
    def load(cls, path: Path) -> "CampaignState":
        if not path.is_file():
            return cls()
        if path.is_symlink():
            raise ValueError("campaign state must not be a symlink")
        if path.stat().st_size > 1_000_000:
            raise ValueError("campaign state exceeds 1 MB safety bound")
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping) or raw.get("schema") != SCHEMA:
            raise ValueError("campaign state schema is unsupported")
        claimed = str(raw.get("state_sha256", ""))
        if claimed:
            payload = dict(raw)
            payload["state_sha256"] = ""
            actual = hashlib.sha256(
                json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
            ).hexdigest()
            if claimed != actual:
                raise ValueError("campaign state integrity digest mismatch")
        allowed = {field.name for field in __import__("dataclasses").fields(cls)}
        return cls(**{key: value for key, value in raw.items() if key in allowed})

    def dump(self, path: Path) -> None:
        self.state_sha256 = ""
        canonical = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), default=str)
        self.state_sha256 = hashlib.sha256(canonical.encode()).hexdigest()
        payload = json.dumps(asdict(self), sort_keys=True, indent=2) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        tmp = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise








def validate_lane_invariants(plan_items: object, team: str) -> None:
    if not isinstance(plan_items, list):
        raise ValueError("canonical plan items must be a list")
    seen: set[str] = set()
    for item in plan_items:
        if not isinstance(item, Mapping) or item.get("target_team") != team:
            continue
        item_id = str(item.get("id", "")).strip()
        if not item_id:
            raise ValueError("canonical team item has empty id")
        if item_id in seen:
            raise ValueError(f"canonical team item id is duplicated: {item_id}")
        seen.add(item_id)
    assignments = lane_assignments(plan_items, team)
    if set(assignments) != seen:
        raise ValueError("lane assignment coverage does not match canonical team graph")


def update_task_age(state: CampaignState, *, plan_items: object, team: str, attempted_task_ids: Sequence[str]) -> None:
    if not isinstance(plan_items, list):
        return
    active = {
        str(item.get("id", "")).strip()
        for item in plan_items
        if isinstance(item, Mapping)
        and item.get("target_team") == team
        and str(item.get("status", "")).lower() == "queued"
        and str(item.get("id", "")).strip()
    }
    attempted = {str(item_id).strip() for item_id in attempted_task_ids}
    next_age: dict[str, int] = {}
    for item_id in sorted(active):
        next_age[item_id] = 0 if item_id in attempted else min(1000, int(state.task_age.get(item_id, 0)) + 1)
    state.task_age = next_age

def dependency_components(plan_items: object, team: str) -> list[list[str]]:
    if not isinstance(plan_items, list):
        return []
    rows = {
        str(item.get("id", "")).strip(): item
        for item in plan_items
        if isinstance(item, Mapping)
        and item.get("target_team") == team
        and str(item.get("id", "")).strip()
    }
    adjacency: dict[str, set[str]] = {key: set() for key in rows}
    for item_id, item in rows.items():
        deps = item.get("dependencies", [])
        if not isinstance(deps, list):
            continue
        for dep in deps:
            dep_id = str(dep).strip()
            if dep_id in rows:
                adjacency[item_id].add(dep_id)
                adjacency[dep_id].add(item_id)
    components: list[list[str]] = []
    unseen = set(rows)
    while unseen:
        root = min(unseen)
        stack = [root]
        component: set[str] = set()
        while stack:
            node = stack.pop()
            if node in component:
                continue
            component.add(node)
            unseen.discard(node)
            stack.extend(sorted(adjacency[node] - component, reverse=True))
        components.append(sorted(component))
    return sorted(components, key=lambda component: component[0] if component else "")


def lane_id(component: Sequence[str]) -> str:
    return hashlib.sha256(
        json.dumps(sorted(component), separators=(",", ":")).encode()
    ).hexdigest()[:16]


def lane_assignments(plan_items: object, team: str) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for component in dependency_components(plan_items, team):
        identifier = lane_id(component)
        for item_id in component:
            assignments[item_id] = identifier
    return assignments

def frontier_digest(frontier: Mapping[str, Any]) -> str:
    payload = {
        "selected": [
            {
                "id": str(item.get("id", "")),
                "priority": item.get("priority", 50),
                "dependencies": item.get("dependencies", []),
            }
            for item in frontier.get("selected", [])
            if isinstance(item, Mapping)
        ],
        "deferred": frontier.get("deferred", []),
        "eligible_count": frontier.get("eligible_count", 0),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()

def select_frontier(
    plan_items: object,
    *,
    team: str,
    cooldowns: Mapping[str, int] | None = None,
    attempts: Mapping[str, int] | None = None,
    lane_health: Mapping[str, Mapping[str, Any]] | None = None,
    task_age: Mapping[str, int] | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    if not 1 <= limit <= 32:
        raise ValueError("frontier limit must be between 1 and 32")
    cooldowns = cooldowns or {}
    attempts = attempts or {}
    lane_health = lane_health or {}
    task_age = task_age or {}
    if not isinstance(plan_items, list):
        raise ValueError("canonical plan items must be a list")
    rows = {
        str(item.get("id", "")).strip(): item
        for item in plan_items
        if isinstance(item, Mapping)
        and item.get("target_team") == team
        and str(item.get("id", "")).strip()
    }
    assignments = lane_assignments(plan_items, team)
    reverse: dict[str, set[str]] = {key: set() for key in rows}
    for item_id, item in rows.items():
        deps = item.get("dependencies", [])
        if isinstance(deps, list):
            for dep in deps:
                dep_id = str(dep).strip()
                if dep_id in reverse:
                    reverse[dep_id].add(item_id)

    def descendants(root: str) -> int:
        seen: set[str] = set()
        stack = list(reverse.get(root, ()))
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            stack.extend(reverse.get(node, ()))
        return len(seen)

    eligible: list[tuple[tuple[int, int, int, str], dict[str, Any]]] = []
    deferred: list[dict[str, Any]] = []
    for item_id, item in rows.items():
        status = str(item.get("status", "queued")).lower()
        if status != "queued":
            continue
        deps = item.get("dependencies", [])
        deps = [str(dep).strip() for dep in deps] if isinstance(deps, list) else []
        unresolved = [
            dep for dep in deps
            if dep not in rows or str(rows[dep].get("status", "")).lower() != "done"
        ]
        cooldown = max(0, int(cooldowns.get(item_id, 0)))
        lane = assignments.get(item_id, "")
        if str(lane_health.get(lane, {}).get("status", "")) == "quarantined":
            deferred.append({"id": item_id, "reason": "lane_quarantined", "lane": lane})
            continue
        if unresolved:
            deferred.append({"id": item_id, "reason": "dependencies", "dependencies": unresolved})
            continue
        if cooldown:
            deferred.append({"id": item_id, "reason": "cooldown", "cycles_remaining": cooldown})
            continue
        try:
            priority = int(item.get("priority", 50))
        except (TypeError, ValueError):
            priority = 50
        priority = max(1, min(100, priority))
        unlock = descendants(item_id)
        attempt_count = max(0, int(attempts.get(item_id, 0)))
        age = max(0, min(1000, int(task_age.get(item_id, 0))))
        score = (-unlock, -age, -priority, attempt_count, item_id)
        enriched = dict(item)
        enriched["_campaign_lane"] = assignments.get(item_id, "")
        eligible.append((score, enriched))

    eligible.sort(key=lambda row: row[0])
    selected: list[dict[str, Any]] = []
    used_roots: set[str] = set()
    used_lanes: set[str] = set()
    remaining = eligible[:]
    # First pass favors independent top-level dependency lanes.
    for score, item in eligible:
        deps = item.get("dependencies", [])
        root = str(deps[0]) if isinstance(deps, list) and deps else str(item.get("id", ""))
        lane = str(item.get("_campaign_lane", ""))
        if root in used_roots or lane in used_lanes:
            continue
        selected.append(item)
        used_roots.add(root)
        used_lanes.add(lane)
        remaining.remove((score, item))
        if len(selected) >= limit:
            break
    # Fill remaining capacity deterministically by unblock value/priority/attempts/id.
    if len(selected) < limit:
        selected.extend(item for _, item in remaining[: limit - len(selected)])
    result = {
        "selected": selected,
        "deferred": sorted(deferred, key=lambda row: (row["reason"], row["id"])),
        "eligible_count": len(eligible),
    }
    result["frontier_sha256"] = frontier_digest(result)
    return result


def allocate_supervisor_state(
    repo_state: dict[str, Any],
    campaign: CampaignState,
    *,
    limit: int = 8,
) -> dict[str, Any]:
    supervisor = repo_state.get("_shift_supervisor")
    if canonical_queue_drained(supervisor, "night"):
        # A completed producer has no work to allocate; do not issue a lease,
        # forge a generation id, or alter the campaign's authority state.
        return {"status": "canonical_queue_drained", "authorized_plan_ids": []}
    if not isinstance(supervisor, dict) or supervisor.get("status") != "loaded":
        raise ValueError("loaded canonical supervisor state is required for allocation")
    validate_lane_invariants(repo_state.get("_shift_supervisor_all_plan_items", []), str(supervisor.get("team", "")))
    generation = str(supervisor.get("generation_id", ""))
    plan_digest = str(supervisor.get("plan_digest_sha256", ""))
    if not generation or len(plan_digest) != 64:
        raise ValueError("canonical supervisor identity is malformed")
    frontier = select_frontier(
        repo_state.get("_shift_supervisor_all_plan_items", []),
        team=str(supervisor.get("team", "")),
        cooldowns=campaign.task_cooldowns,
        attempts=campaign.task_attempts,
        lane_health=campaign.lane_health,
        task_age=campaign.task_age,
        limit=limit,
    )
    selected = frontier["selected"]
    lane_map = {
        str(item.get("id", "")): str(item.get("_campaign_lane", ""))
        for item in selected
    }
    selected_ids = {str(item.get("id", "")) for item in selected}
    executable = supervisor.get("plan_items", [])
    if not isinstance(executable, list):
        raise ValueError("canonical executable plan is malformed")
    authorized = [
        dict(item) for item in executable
        if isinstance(item, Mapping) and str(item.get("id", "")) in selected_ids
    ]
    authorized_ids = {str(item.get("id", "")) for item in authorized}
    if authorized_ids != selected_ids:
        unavailable = sorted(selected_ids - authorized_ids)
        raise ValueError(f"frontier selected non-executable canonical items: {unavailable}")
    allocation_nonce = hashlib.sha256(
        f"{campaign.campaign_id}:{campaign.epoch}:{generation}:{frontier['frontier_sha256']}".encode()
    ).hexdigest()[:24]
    allocation = {
        "schema": "autonomous-studio.frontier-allocation.v1",
        "campaign_id": campaign.campaign_id,
        "campaign_epoch": campaign.epoch,
        "allocation_nonce": allocation_nonce,
        "generation_id": generation,
        "plan_digest_sha256": plan_digest,
        "frontier_sha256": frontier["frontier_sha256"],
        "authorized_plan_ids": sorted(authorized_ids),
        "lane_assignments": {item_id: lane_map[item_id] for item_id in sorted(authorized_ids)},
    }
    allocation["allocation_sha256"] = hashlib.sha256(
        json.dumps(allocation, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    campaign.last_allocation_sha256 = allocation["allocation_sha256"]
    supervisor["plan_items"] = authorized
    supervisor["allocation"] = allocation
    repo_state["_shift_supervisor"] = supervisor
    return allocation

def acquire_lease(state: CampaignState, *, owner: str, expected_epoch: int | None = None) -> CampaignState:
    owner = str(owner).strip()
    if not owner or len(owner) > 160 or any(ord(ch) < 32 for ch in owner):
        raise ValueError("campaign lease owner is malformed")
    if expected_epoch is not None and state.epoch != expected_epoch:
        raise ValueError("campaign epoch compare-and-swap failed")
    if state.lease_owner and state.lease_owner != owner:
        raise ValueError("campaign lease is owned by another controller")
    state.lease_owner = owner
    state.lease_epoch = state.epoch
    return state


def release_lease(state: CampaignState, *, owner: str) -> CampaignState:
    if state.lease_owner != owner:
        raise ValueError("campaign lease release owner mismatch")
    state.lease_owner = ""
    state.lease_epoch = state.epoch
    return state

def dependency_diagnostics(plan_items: object, team: str) -> dict[str, Any]:
    if not isinstance(plan_items, list):
        return {"blocked": [], "cycles": [], "missing_dependencies": []}
    rows = {
        str(item.get("id", "")).strip(): item
        for item in plan_items
        if isinstance(item, Mapping)
        and item.get("target_team") == team
        and str(item.get("id", "")).strip()
    }
    blocked: list[str] = []
    missing: list[dict[str, str]] = []
    graph: dict[str, list[str]] = {}
    for item_id, item in rows.items():
        deps = item.get("dependencies", [])
        deps = [str(dep).strip() for dep in deps] if isinstance(deps, list) else []
        graph[item_id] = [dep for dep in deps if dep in rows]
        if str(item.get("status", "")).lower() not in {"done", "rejected"}:
            unresolved = [
                dep for dep in deps
                if dep not in rows or str(rows[dep].get("status", "")).lower() != "done"
            ]
            if unresolved:
                blocked.append(item_id)
            for dep in unresolved:
                if dep not in rows:
                    missing.append({"item_id": item_id, "dependency_id": dep})

    cycles: list[list[str]] = []
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> None:
        if node in visiting:
            if node in stack:
                cycle = stack[stack.index(node):] + [node]
                normalized = cycle[:-1]
                if normalized:
                    pivot = min(range(len(normalized)), key=lambda i: normalized[i])
                    canonical = normalized[pivot:] + normalized[:pivot]
                    if canonical not in cycles:
                        cycles.append(canonical)
            return
        if node in visited:
            return
        visiting.add(node)
        stack.append(node)
        for dep in graph.get(node, []):
            visit(dep)
        stack.pop()
        visiting.remove(node)
        visited.add(node)

    for node in sorted(graph):
        visit(node)
    return {
        "blocked": sorted(set(blocked)),
        "cycles": sorted(cycles),
        "missing_dependencies": sorted(missing, key=lambda row: (row["item_id"], row["dependency_id"])),
    }

def campaign_identity(supervisor: Mapping[str, Any]) -> str:
    payload = {
        "team": supervisor.get("team"),
        "issue_number": supervisor.get("issue_number"),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()[:24]



def update_lane_health(
    state: CampaignState,
    *,
    plan_items: object,
    attempted_task_ids: Sequence[str],
    validation_failed: bool,
) -> None:
    assignments = lane_assignments(plan_items, "night")
    attempted_lanes = {assignments[item_id] for item_id in attempted_task_ids if item_id in assignments}
    for lane in attempted_lanes:
        health = dict(state.lane_health.get(lane, {}))
        health["attempt_cycles"] = int(health.get("attempt_cycles", 0)) + 1
        if validation_failed:
            health["failures"] = int(health.get("failures", 0)) + 1
        else:
            health["failures"] = int(health.get("failures", 0))
        health["status"] = "quarantined" if health["failures"] >= 3 else "healthy"
        state.lane_health[lane] = health
    if len(state.lane_health) > 128:
        state.lane_health = {
            key: state.lane_health[key] for key in sorted(state.lane_health)[:128]
        }

def advance_campaign(
    state: CampaignState,
    *,
    supervisor: Mapping[str, Any],
    validated_patch: bool,
    validation_failed: bool,
    attempted_task_ids: Sequence[str] = (),
    plan_items: object = None,
    policy: CampaignPolicy | None = None,
) -> CampaignState:
    policy = policy or CampaignPolicy()
    policy.validate()
    if state.status in TERMINAL_STATES:
        return state

    identity = campaign_identity(supervisor)
    if state.campaign_id and state.campaign_id != identity:
        state = CampaignState(campaign_id=identity)
    elif not state.campaign_id:
        state.campaign_id = identity

    progress = supervisor.get("progress", {})
    if not isinstance(progress, Mapping):
        raise ValueError("supervisor progress is missing")
    fingerprint = str(progress.get("fingerprint_sha256", ""))
    if len(fingerprint) != 64:
        raise ValueError("supervisor progress fingerprint is malformed")

    state.cycle += 1
    state.epoch += 1
    generation = str(supervisor.get("generation_id", ""))
    progressed = bool(state.last_progress_fingerprint and fingerprint != state.last_progress_fingerprint)
    if progressed:
        state.stagnant_cycles = 0
    elif state.last_progress_fingerprint:
        state.stagnant_cycles += 1

    if validation_failed:
        state.failures += 1

    if len(attempted_task_ids) > 32:
        raise ValueError("campaign cycle exceeds 32 attempted tasks")
    for key in list(state.task_cooldowns):
        remaining = max(0, int(state.task_cooldowns[key]) - 1)
        if remaining:
            state.task_cooldowns[key] = remaining
        else:
            state.task_cooldowns.pop(key, None)

    for task_id in attempted_task_ids:
        key = str(task_id).strip()
        if len(key) > 160:
            raise ValueError("campaign task id exceeds 160 characters")
        if key:
            state.task_attempts[key] = state.task_attempts.get(key, 0) + 1
            attempts = state.task_attempts[key]
            if attempts > 1:
                state.task_cooldowns[key] = min(8, 2 ** min(3, attempts - 1))

    update_task_age(
        state,
        plan_items=plan_items,
        team=str(supervisor.get("team", "")),
        attempted_task_ids=attempted_task_ids,
    )
    update_lane_health(
        state,
        plan_items=plan_items,
        attempted_task_ids=attempted_task_ids,
        validation_failed=validation_failed,
    )
    diagnostics = dependency_diagnostics(plan_items, str(supervisor.get("team", "")))
    terminal = bool(progress.get("terminal", False)) or supervisor.get("status") == "complete"
    if terminal:
        state.status = "complete"
        state.terminal_reason = "canonical_queue_drained"
    elif diagnostics["cycles"]:
        state.status = "quarantined"
        state.terminal_reason = "dependency_cycle_detected"
    elif diagnostics["missing_dependencies"]:
        state.status = "quarantined"
        state.terminal_reason = "missing_dependency_detected"
    elif any(count > policy.max_task_attempts for count in state.task_attempts.values()):
        state.status = "quarantined"
        state.terminal_reason = "task_attempt_budget_exceeded"
    elif state.failures >= policy.max_failures:
        state.status = "quarantined"
        state.terminal_reason = "validation_failure_budget_exceeded"
    elif state.stagnant_cycles >= policy.max_stagnant_cycles:
        state.status = "quarantined"
        state.terminal_reason = "no_progress_budget_exceeded"
    elif state.cycle >= policy.max_cycles:
        state.status = "exhausted"
        state.terminal_reason = "campaign_cycle_budget_exceeded"
    elif validated_patch:
        state.status = "continue"
    else:
        state.status = "waiting"

    state.last_progress_fingerprint = fingerprint
    state.last_generation_id = generation
    state.history.append(
        {
            "cycle": state.cycle,
            "generation_id": generation,
            "progress_fingerprint_sha256": fingerprint,
            "validated_patch": validated_patch,
            "validation_failed": validation_failed,
            "status": state.status,
            "terminal_reason": state.terminal_reason,
            "dependency_diagnostics": diagnostics,
        }
    )
    state.history = state.history[-MAX_HISTORY:]
    if len(state.task_attempts) > 512:
        active = sorted(state.task_attempts.items(), key=lambda pair: (-pair[1], pair[0]))[:512]
        state.task_attempts = dict(active)
    state.task_cooldowns = {
        key: value for key, value in state.task_cooldowns.items() if key in state.task_attempts
    }
    return state


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bounded Autonomous Studio completion campaign controller")
    parser.add_argument("--state", required=True)
    parser.add_argument("--repo-state", required=True)
    parser.add_argument("--validated-patch", action="store_true")
    parser.add_argument("--validation-failed", action="store_true")
    parser.add_argument("--attempted-task", action="append", default=[])
    parser.add_argument("--max-cycles", type=int, default=40)
    parser.add_argument("--max-stagnant-cycles", type=int, default=3)
    parser.add_argument("--max-failures", type=int, default=5)
    parser.add_argument("--max-task-attempts", type=int, default=4)
    parser.add_argument("--frontier")
    parser.add_argument("--frontier-limit", type=int, default=8)
    parser.add_argument("--allocate", action="store_true")
    parser.add_argument("--advance", action="store_true")
    parser.add_argument("--lease-owner", default=os.environ.get("GITHUB_RUN_ID", "local"))
    parser.add_argument("--expected-epoch", type=int)
    args = parser.parse_args(argv)

    repo_state = json.loads(Path(args.repo_state).read_text(encoding="utf-8"))
    supervisor = repo_state.get("_shift_supervisor", {})
    if not isinstance(supervisor, Mapping):
        raise SystemExit("canonical supervisor state missing")
    state_path = Path(args.state)
    state = CampaignState.load(state_path)
    if args.allocate:
        allocation = allocate_supervisor_state(repo_state, state, limit=args.frontier_limit)
        repo_path = Path(args.repo_state)
        repo_path.write_text(json.dumps(repo_state, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if args.frontier:
        frontier = select_frontier(
            repo_state.get("_shift_supervisor_all_plan_items", []),
            team=str(supervisor.get("team", "")),
            cooldowns=state.task_cooldowns,
            attempts=state.task_attempts,
            lane_health=state.lane_health,
            task_age=state.task_age,
            limit=args.frontier_limit,
        )
        Path(args.frontier).write_text(json.dumps(frontier, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    if not args.advance:
        state.dump(state_path)
        print(json.dumps(asdict(state), sort_keys=True))
        return 0

    state = acquire_lease(state, owner=args.lease_owner, expected_epoch=args.expected_epoch)
    state = advance_campaign(
        state,
        supervisor=supervisor,
        validated_patch=args.validated_patch,
        validation_failed=args.validation_failed,
        attempted_task_ids=args.attempted_task,
        plan_items=repo_state.get("_shift_supervisor_all_plan_items"),
        policy=CampaignPolicy(
            max_cycles=args.max_cycles,
            max_stagnant_cycles=args.max_stagnant_cycles,
            max_failures=args.max_failures,
            max_task_attempts=args.max_task_attempts,
        ),
    )
    state = release_lease(state, owner=args.lease_owner)
    state.dump(state_path)
    print(json.dumps(asdict(state), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
