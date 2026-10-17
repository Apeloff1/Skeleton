"""Schedule studio tasks across role agents.

The scheduler owns checkpoints and repair. It uses the canonical swarm DAG
for dependencies and the handoff registry for artefact contracts. A run can
stop after a wave and resume from the checkpoint without repeating finished
roles.
"""

from __future__ import annotations

import copy
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from skeleton.automation.swarm.dag import SwarmDag
from skeleton.automation.swarm.handoff import HandoffRegistry
from skeleton.automation.swarm.studio.agents import HANDLERS, ExecContext
from skeleton.automation.swarm.studio.memory import ProjectMemory, bound_top_k
from skeleton.automation.swarm.studio.planner import ModelClient, PlannedTask, normalize_brief, plan_brief
from skeleton.automation.swarm.studio.roles import StudioRole, validate_capability_output
from skeleton.automation.swarm.studio.tools import StudioTools


CHECKPOINT_SCHEMA = "skeleton.studio.checkpoint.v1"


@dataclass
class StudioControls:
    max_waves: int = 24
    max_repairs: int = 2
    top_k: int = 5
    dry_run: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.max_waves, bool) or not isinstance(self.max_waves, int) or self.max_waves < 1:
            raise ValueError("max_waves must be a positive integer")
        if isinstance(self.max_repairs, bool) or not isinstance(self.max_repairs, int) or self.max_repairs < 0:
            raise ValueError("max_repairs must be a non-negative integer")
        if not isinstance(self.dry_run, bool):
            raise ValueError("dry_run must be a bool")
        self.top_k = bound_top_k(self.top_k)


@dataclass
class StudioReport:
    run_id: str
    status: str
    brief: dict[str, Any]
    tasks: list[dict[str, Any]]
    artefacts: dict[str, dict[str, Any]]
    issues: list[dict[str, Any]]
    playtest: dict[str, Any] | None
    economics: dict[str, Any]
    events: list[dict[str, Any]]
    handoffs: dict[str, Any]
    checkpoint: dict[str, Any]
    score: dict[str, Any]
    execution_counts: dict[str, int] = field(default_factory=dict)


class StudioSession:
    """One brief, one workspace, one resumable production graph."""

    def __init__(
        self,
        brief: Mapping[str, Any],
        workspace: str | Path,
        *,
        controls: StudioControls | None = None,
        model: ModelClient | None = None,
        tools: StudioTools | None = None,
        forge_runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.controls = controls or StudioControls()
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.tools = tools or StudioTools(self.workspace)
        self.model = model
        self.forge_runner = forge_runner
        self._clock = clock or time.time
        self.brief = normalize_brief(dict(brief))
        pitch_rejected = self._sanitize_pitch()
        self.run_id = hashlib.sha256(
            json.dumps(self.brief, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:12]
        self.memory = ProjectMemory(self.run_id, top_k=self.controls.top_k)
        if pitch_rejected:
            self.memory.remember(
                "failure",
                "brief pitch rejected by sandbox",
                tags=["failure", "brief"],
            )
        self.tasks: list[PlannedTask] = []
        self.artefacts: dict[str, dict[str, Any]] = {}
        self.execution_counts: dict[str, int] = {}
        self.events: list[dict[str, Any]] = []
        self.issues: list[dict[str, Any]] = []
        self.latest_playtest: dict[str, Any] | None = None
        self.repairs_done = 0
        self.model_calls = 0
        self.waves_run = 0
        self._files: dict[str, str] = {}
        self._snapshots: list[dict[str, Any]] = []
        self._phase = "new"
        self._last_report: StudioReport | None = None
        self.dag = SwarmDag()
        self.handoffs = HandoffRegistry(clock=self._clock)
        findings = self.tools.preflight_corpus()
        self._preflight_ok = not findings
        if findings:
            self._event("preflight", "injection corpus findings")

    def run(self, *, max_waves: int | None = None) -> StudioReport:
        if self._phase == "completed" and self._last_report is not None:
            return self._last_report
        if not self._preflight_ok:
            return self._finish("failed")
        self._ensure_plan()
        if self.controls.dry_run:
            self._event("planned", "dry run")
            return self._finish("planned")
        limit = self.controls.max_waves if max_waves is None else max_waves
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("max_waves must be a positive integer")
        return self._drain(limit)

    def resume(self, checkpoint: Mapping[str, Any], *, max_waves: int | None = None) -> StudioReport:
        self._load_checkpoint(checkpoint)
        if not self._preflight_ok:
            return self._finish("failed")
        limit = self.controls.max_waves if max_waves is None else max_waves
        return self._drain(limit)

    def rollback(self, wave: int) -> StudioReport:
        if isinstance(wave, bool) or not isinstance(wave, int) or wave < 0 or wave >= len(self._snapshots):
            raise ValueError("wave is outside the checkpoint log")
        snap = copy.deepcopy(self._snapshots[wave])
        self.tasks = [PlannedTask.from_dict(item) for item in snap["tasks"]]
        self.artefacts = snap["completed"]
        self._files = snap["files"]
        self.repairs_done = snap["repairs"]
        self.latest_playtest = snap["playtest"]
        self.issues = snap["issues"]
        self.memory.restore(snap["memory"])
        self._rebuild_dag()
        self._phase = "rolled_back"
        self._event("rollback", f"wave {wave}")
        report = self._finish("rolled_back")
        self._phase = "rolled_back"
        return report

    def _sanitize_pitch(self) -> bool:
        pitch = self.brief.get("pitch")
        if not isinstance(pitch, str) or not pitch.strip():
            self.brief["pitch"] = ""
            return False
        decision = self.tools.sandbox.ingest_untrusted(pitch)
        if decision.allowed:
            return False
        self.brief["pitch"] = ""
        return True

    def _ensure_plan(self) -> None:
        if self.tasks:
            return
        if self.model is not None:
            self.model_calls += 1
        self.tasks = list(plan_brief(self.brief, model=self.model))
        self._rebuild_dag()
        self._event("planned", f"{len(self.tasks)} tasks")
        self._snapshot()

    def _rebuild_dag(self) -> None:
        done = set(self.artefacts)
        self.dag = SwarmDag()
        for task in self.tasks:
            if task.id in done:
                continue
            deps = [dep for dep in task.deps if dep not in done]
            self.dag.submit(task.id, task.capability, {"goal": task.goal}, deps)

    def _drain(self, limit: int) -> StudioReport:
        if not self._snapshots:
            self._snapshot()
        waves = 0
        while waves < limit:
            wave = self.dag.ready_wave()
            if not wave:
                break
            waves += 1
            self.waves_run += 1
            finished: list[str] = []
            self._event("wave", ",".join(task.id for task in wave))
            for task in wave:
                claimed = self.dag.claim(task.id, "studio-scheduler")
                if claimed is None:
                    continue
                artefact = self._execute(claimed.id, claimed.capability)
                if artefact is None or not self.dag.complete(claimed.id, artefact):
                    self.dag.fail(claimed.id)
                    self._event("failed", claimed.id)
                else:
                    self.artefacts[claimed.id] = artefact
                    finished.append(claimed.id)
            self._snapshot()
            self._schedule_repairs(finished)
        status = self._status(stopped_early=waves >= limit and not self._graph_settled())
        return self._finish(status)

    def _execute(self, task_id: str, capability: str) -> dict[str, Any] | None:
        handler = HANDLERS.get(capability)
        role = self._role_for(task_id, capability)
        envelope = self.handoffs.submit(
            capability,
            {"task": task_id, "brief": self.brief["title"]},
            requester="studio-scheduler",
        )
        self.handoffs.accept(envelope.task_id, assignee=role)
        if handler is None:
            self.handoffs.fail(envelope.task_id, "no handler")
            return None
        ctx = ExecContext(
            brief=self.brief,
            artefacts=self.artefacts,
            memory=self.memory,
            tools=self.tools,
            forge_runner=self.forge_runner,
        )
        try:
            artefact = handler(ctx)
            validate_capability_output(capability, artefact)
        except Exception:
            self.memory.remember("failure", f"{task_id} failed closed", tags=["failure", role])
            self.handoffs.fail(envelope.task_id, "handler failed")
            return None
        self.execution_counts[role] = self.execution_counts.get(role, 0) + 1
        if capability == "studio.repair":
            self.repairs_done += 1
        if capability == "studio.qa":
            self.latest_playtest = _playtest_view(artefact)
            self.issues = list(artefact.get("issues") or [])
            self._event("playtest", "won" if artefact.get("won") else "open")
        self.handoffs.complete(envelope.task_id, artefacts=[{"id": task_id, "uri": f"studio://{task_id}"}])
        self._event("handoff", f"{role} {capability}")
        self._files.update(self.tools.writes)
        return dict(artefact)

    def _schedule_repairs(self, finished: list[str]) -> None:
        qa_ids = [task_id for task_id in finished if task_id == "qa" or task_id.startswith("qa-")]
        if not qa_ids or not self.latest_playtest or self.latest_playtest.get("won"):
            return
        blockers = [issue for issue in self.issues if issue.get("severity") == "blocker"]
        if not blockers:
            return
        if self.repairs_done >= self.controls.max_repairs:
            return
        if any(task.id.startswith("repair-") and task.id not in self.artefacts for task in self.tasks):
            return
        number = self.repairs_done + 1
        repair_id = f"repair-{number}"
        qa_id = f"qa-{number + 1}"
        source = qa_ids[-1]
        repair = PlannedTask(
            repair_id,
            StudioRole.SYSTEMS,
            "studio.repair",
            (source,),
            "Repair the playable from QA issues",
        )
        follow = PlannedTask(qa_id, StudioRole.QA, "studio.qa", (repair_id,), "Replay the repaired build")
        self.tasks.extend([repair, follow])
        self.dag.submit(repair.id, repair.capability, {"goal": repair.goal}, list(repair.deps))
        self.dag.submit(follow.id, follow.capability, {"goal": follow.goal}, list(follow.deps))
        self._event("repair", repair_id)

    def _status(self, *, stopped_early: bool) -> str:
        if stopped_early and not self._graph_settled():
            return "partial"
        if self.latest_playtest and self.latest_playtest.get("won") and self._graph_settled():
            return "completed"
        if self.latest_playtest and not self.latest_playtest.get("won") and self._graph_settled():
            return "failed"
        if self._graph_settled():
            return "completed" if self.latest_playtest and self.latest_playtest.get("won") else "failed"
        return "partial"

    def _graph_settled(self) -> bool:
        pending = [task for task in self.tasks if task.id not in self.artefacts]
        if not pending:
            return True
        stats = self.dag.stats().get("by_status", {})
        return not stats.get("pending") and not stats.get("ready") and not stats.get("running")

    def _snapshot(self) -> None:
        self._files.update(self.tools.writes)
        self._snapshots.append(
            {
                "wave": len(self._snapshots),
                "tasks": [task.to_dict() for task in self.tasks],
                "completed": copy.deepcopy(self.artefacts),
                "files": dict(self._files),
                "repairs": self.repairs_done,
                "playtest": copy.deepcopy(self.latest_playtest),
                "issues": copy.deepcopy(self.issues),
                "memory": self.memory.snapshot(),
            }
        )
        self._event("checkpoint", f"wave {len(self._snapshots) - 1}")

    def checkpoint(self) -> dict[str, Any]:
        self._files.update(self.tools.writes)
        return {
            "schema": CHECKPOINT_SCHEMA,
            "run_id": self.run_id,
            "brief": dict(self.brief),
            "tasks": [task.to_dict() for task in self.tasks],
            "completed": copy.deepcopy(self.artefacts),
            "issues": copy.deepcopy(self.issues),
            "playtest": copy.deepcopy(self.latest_playtest),
            "repairs": self.repairs_done,
            "wave": max(len(self._snapshots) - 1, 0),
            "memory": self.memory.snapshot(),
            "files": dict(self._files),
            "snapshots": copy.deepcopy(self._snapshots),
            "events": list(self.events),
            "economics": self._economics(),
        }

    def _load_checkpoint(self, checkpoint: Mapping[str, Any]) -> None:
        if checkpoint.get("schema") != CHECKPOINT_SCHEMA:
            raise ValueError("unsupported checkpoint schema")
        brief = checkpoint.get("brief")
        if isinstance(brief, Mapping):
            self.brief = normalize_brief(brief)
        self.run_id = str(checkpoint.get("run_id") or self.run_id)
        self.tasks = [PlannedTask.from_dict(item) for item in checkpoint.get("tasks") or []]
        completed = checkpoint.get("completed") if isinstance(checkpoint.get("completed"), Mapping) else {}
        self.artefacts = {str(key): dict(value) for key, value in completed.items() if isinstance(value, Mapping)}
        self.issues = [dict(item) for item in checkpoint.get("issues") or [] if isinstance(item, dict)]
        playtest = checkpoint.get("playtest")
        self.latest_playtest = dict(playtest) if isinstance(playtest, Mapping) else None
        repairs = checkpoint.get("repairs") or 0
        self.repairs_done = repairs if isinstance(repairs, int) and not isinstance(repairs, bool) else 0
        files = checkpoint.get("files") if isinstance(checkpoint.get("files"), Mapping) else {}
        self._files = {str(key): str(value) for key, value in files.items()}
        self.memory = ProjectMemory(self.run_id, top_k=self.controls.top_k)
        self.memory.restore(list(checkpoint.get("memory") or []))
        self.events = [dict(item) for item in checkpoint.get("events") or [] if isinstance(item, dict)]
        snapshots = checkpoint.get("snapshots")
        self._snapshots = copy.deepcopy(snapshots) if isinstance(snapshots, list) else []
        self.handoffs = HandoffRegistry(clock=self._clock)
        self.execution_counts = {}
        self.waves_run = 0
        self._phase = "resumed"
        self._restore_files()
        self._rebuild_dag()

    def _restore_files(self) -> None:
        for relative, content in self._files.items():
            path = self.workspace / relative
            if not path.is_file():
                self.tools.write_text(relative, content)

    def _finish(self, status: str) -> StudioReport:
        report = StudioReport(
            run_id=self.run_id,
            status=status,
            brief=dict(self.brief),
            tasks=[task.to_dict() for task in self.tasks],
            artefacts=copy.deepcopy(self.artefacts),
            issues=copy.deepcopy(self.issues),
            playtest=copy.deepcopy(self.latest_playtest),
            economics=self._economics(),
            events=list(self.events),
            handoffs=self.handoffs.stats(),
            checkpoint=self.checkpoint(),
            score=score_report(self.tasks, self.latest_playtest, self.workspace),
            execution_counts=dict(self.execution_counts),
        )
        self._last_report = report
        if status == "completed":
            self._phase = "completed"
        elif status == "rolled_back":
            self._phase = "rolled_back"
        else:
            self._phase = status
        return report

    def _economics(self) -> dict[str, Any]:
        units = 0
        for artefact in self.artefacts.values():
            units += max(len(json.dumps(artefact, default=str)) // 4, 1)
        return {
            "waves": self.waves_run,
            "tool_calls": self.tools.tool_calls,
            "denied_tools": self.tools.denied_tools,
            "repairs": self.repairs_done,
            "model_calls": self.model_calls,
            "estimated_units": units,
        }

    def _event(self, kind: str, detail: str) -> None:
        self.events.append({"kind": kind, "detail": detail, "at": self._clock()})

    def _role_for(self, task_id: str, capability: str) -> str:
        for task in self.tasks:
            if task.id == task_id:
                return task.role.value
        if capability == "studio.qa":
            return StudioRole.QA.value
        return StudioRole.SYSTEMS.value


def score_report(
    tasks: list[PlannedTask] | list[Mapping[str, Any]],
    playtest: Mapping[str, Any] | None,
    workspace: Path,
) -> dict[str, Any]:
    planned = 1 if tasks else 0
    built = 1 if (workspace / "playable.json").is_file() else 0
    boots = 1 if playtest and playtest.get("booted") else 0
    loop_works = 1 if playtest and playtest.get("loop_works") else 0
    coverage_score = float(playtest.get("spec_coverage")) if playtest else 0.0
    total = (planned + built + boots + loop_works + coverage_score) / 5
    return {
        "planned": planned,
        "built": built,
        "boots": boots,
        "loop_works": loop_works,
        "spec_coverage": coverage_score,
        "total": total,
    }


def _playtest_view(artefact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "booted": bool(artefact.get("booted")),
        "ticks": int(artefact.get("ticks") or 0),
        "verbs": list(artefact.get("verbs") or []),
        "loop_works": bool(artefact.get("loop_works")),
        "won": bool(artefact.get("won")),
        "spec_coverage": float(artefact.get("spec_coverage") or 0.0),
        "issues": list(artefact.get("issues") or []),
    }
