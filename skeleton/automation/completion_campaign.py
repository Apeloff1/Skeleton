from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

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


def advance_campaign(
    state: CampaignState,
    *,
    supervisor: Mapping[str, Any],
    validated_patch: bool,
    validation_failed: bool,
    attempted_task_ids: Sequence[str] = (),
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
    for task_id in attempted_task_ids:
        key = str(task_id).strip()
        if len(key) > 160:
            raise ValueError("campaign task id exceeds 160 characters")
        if key:
            state.task_attempts[key] = state.task_attempts.get(key, 0) + 1

    terminal = bool(progress.get("terminal", False)) or supervisor.get("status") == "complete"
    if terminal:
        state.status = "complete"
        state.terminal_reason = "canonical_queue_drained"
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
        }
    )
    state.history = state.history[-MAX_HISTORY:]
    if len(state.task_attempts) > 512:
        active = sorted(state.task_attempts.items(), key=lambda pair: (-pair[1], pair[0]))[:512]
        state.task_attempts = dict(active)
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
    args = parser.parse_args(argv)

    repo_state = json.loads(Path(args.repo_state).read_text(encoding="utf-8"))
    supervisor = repo_state.get("_shift_supervisor", {})
    if not isinstance(supervisor, Mapping):
        raise SystemExit("canonical supervisor state missing")
    state_path = Path(args.state)
    state = CampaignState.load(state_path)
    state = advance_campaign(
        state,
        supervisor=supervisor,
        validated_patch=args.validated_patch,
        validation_failed=args.validation_failed,
        attempted_task_ids=args.attempted_task,
        policy=CampaignPolicy(
            max_cycles=args.max_cycles,
            max_stagnant_cycles=args.max_stagnant_cycles,
            max_failures=args.max_failures,
            max_task_attempts=args.max_task_attempts,
        ),
    )
    state.dump(state_path)
    print(json.dumps(asdict(state), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
