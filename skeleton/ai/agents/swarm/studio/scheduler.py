"""Schedule studio planning waves, then hand the brief to the game builder.

The session is the planner/QA hook pair for ``build_playable_game``. Planning
notes are checkpointed on disk. Rollback rewrites the workspace to the chosen
wave, including files that changed after the snapshot and files created later.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skeleton.automation.swarm.dag import SwarmDag, TaskStatus
from skeleton.automation.swarm.handoff import HandoffRegistry
from skeleton.automation.swarm.studio.agents import HANDLERS, ExecContext, run_qa
from skeleton.automation.swarm.studio.checkpoint import (
    CHECKPOINT_SCHEMA,
    CheckpointError,
    capture_tree,
    load_manifest,
    materialize,
    save_manifest,
    store_blobs,
)
from skeleton.automation.swarm.studio.memory import ProjectMemory, bound_top_k
from skeleton.automation.swarm.studio.planner import (
    ModelClient,
    PlannedTask,
    apply_plan,
    plan_brief,
)
from skeleton.automation.swarm.studio.playtester import review_build, score_build
from skeleton.automation.swarm.studio.roles import (
    StudioContractError,
    validate_capability_output,
)
from skeleton.automation.swarm.studio.tools import StudioTools, ToolError

Builder = Callable[..., Mapping[str, Any]]
SESSION_BUDGET_S = 120.0


@dataclass
class StudioControls:
    max_waves: int = 24
    max_repairs: int = 2
    top_k: int = 5
    dry_run: bool = False
    playtest_mode: str = "off"
    budget_s: float = SESSION_BUDGET_S

    def __post_init__(self) -> None:
        if isinstance(self.max_waves, bool) or not isinstance(self.max_waves, int) or not 1 <= self.max_waves <= 24:
            raise ValueError("max_waves must be an integer from 1 to 24")
        if isinstance(self.max_repairs, bool) or not isinstance(self.max_repairs, int) or not 0 <= self.max_repairs <= 2:
            raise ValueError("max_repairs must be an integer from 0 to 2")
        if not isinstance(self.dry_run, bool):
            raise TypeError("dry_run must be a bool")
        if self.playtest_mode not in {"off", "auto", "require"}:
            raise ValueError("playtest_mode must be off, auto, or require")
        if isinstance(self.budget_s, bool) or not isinstance(self.budget_s, (int, float)):
            raise TypeError("budget_s must be a number")
        if not 0 < float(self.budget_s) <= SESSION_BUDGET_S:
            raise ValueError("budget_s must be greater than 0 and at most 120 seconds")
        self.budget_s = float(self.budget_s)
        self.top_k = bound_top_k(self.top_k)


@dataclass
class StudioReport:
    run_id: str
    status: str
    brief: str
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
    """One brief, one workspace, one resumable planning graph, one builder call."""

    def __init__(
        self,
        brief: str | Mapping[str, Any],
        workspace: str | Path,
        *,
        controls: StudioControls | None = None,
        model: ModelClient | None = None,
        tools: StudioTools | None = None,
        clock: Callable[[], float] | None = None,
        builder: Builder | None = None,
    ) -> None:
        self.controls = controls or StudioControls()
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.tools = tools or StudioTools(self.workspace)
        self.model = model
        self._clock = clock or time.time
        self._started = self._clock()
        self._builder = builder or _default_builder
        self.brief_text = _brief_text(brief)
        self.rejected = self._sanitize_brief()
        self.run_id = hashlib.sha256(self.brief_text.encode("utf-8")).hexdigest()[:12]
        self.memory = ProjectMemory(self.run_id or "studio", top_k=self.controls.top_k)
        if self.rejected:
            self.memory.remember("failure", "brief rejected by sandbox", tags=["failure", "brief"])
        self.spec: dict[str, Any] = {}
        self.tasks: list[PlannedTask] = []
        self.artefacts: dict[str, dict[str, Any]] = {}
        self.execution_counts: dict[str, int] = {}
        self.events: list[dict[str, Any]] = []
        self.issues: list[dict[str, Any]] = []
        self.latest_playtest: dict[str, Any] | None = None
        self.repairs_done = 0
        self.model_calls = 0
        self.waves_run = 0
        self._waves: list[dict[str, Any]] = []
        self._build: dict[str, Any] | None = None
        self._phase = "new"
        self._last_report: StudioReport | None = None
        self.dag = SwarmDag()
        self.handoffs = HandoffRegistry(clock=self._clock)
        findings = self.tools.preflight_corpus()
        self._preflight_ok = not findings
        if findings:
            self._event("preflight", "injection corpus findings")

    @classmethod
    def open(cls, workspace: str | Path, **kwargs: Any) -> StudioSession:
        """Load a session from the on-disk checkpoint and restore its files."""
        data = load_manifest(Path(workspace))
        brief = data.get("brief")
        session = cls(brief if isinstance(brief, str) else "", workspace, **kwargs)
        session._load(data)
        return session

    def run(self, *, max_waves: int | None = None) -> StudioReport:
        if self._phase == "completed" and self._last_report is not None:
            return self._last_report
        if self.rejected:
            self._persist()
            return self._finish("rejected")
        if self._over_budget():
            self._persist()
            return self._finish("budget")
        self._ensure_tasks()
        self._drain(max_waves)
        self._persist()
        if not self._plan_complete():
            return self._finish("partial")
        if self.controls.dry_run:
            return self._finish("dry_run")
        if self._over_budget():
            return self._finish("budget")
        if self._build is None:
            self._build = dict(
                self._builder(
                    self.brief_text,
                    planner=self.as_planner,
                    qa=self.as_qa,
                    playtest_mode=self.controls.playtest_mode,
                    out=str(self.workspace / "project"),
                )
            )
            self._persist()
        return self._finish(self._status())

    def resume(self, *, max_waves: int | None = None) -> StudioReport:
        if not self._waves:
            try:
                self._load(load_manifest(self.workspace))
            except (CheckpointError, OSError, ValueError) as exc:
                self._event("resume", f"checkpoint not loaded: {exc}"[:200])
        return self.run(max_waves=max_waves)

    def rollback(self, wave: int) -> StudioReport:
        """Revert workspace bytes to a persisted wave, including later edits."""
        if isinstance(wave, bool) or not isinstance(wave, int) or wave < 0 or wave >= len(self._waves):
            raise ValueError("unknown checkpoint wave")
        chosen = self._waves[wave]
        files = chosen.get("files") if isinstance(chosen.get("files"), Mapping) else {}
        materialize(self.workspace, {str(key): str(value) for key, value in files.items()})
        self._waves = self._waves[: wave + 1]
        self.artefacts = {
            str(key): dict(value)
            for key, value in (chosen.get("artefacts") or {}).items()
            if isinstance(value, Mapping)
        }
        self.issues = [dict(item) for item in chosen.get("issues") or [] if isinstance(item, dict)]
        repairs = chosen.get("repairs") or 0
        self.repairs_done = repairs if isinstance(repairs, int) and not isinstance(repairs, bool) else 0
        self.memory = ProjectMemory(self.run_id or "studio", top_k=self.controls.top_k)
        self.memory.restore(list(chosen.get("memory") or []))
        self._build = None
        self.latest_playtest = None
        self._phase = "rolled_back"
        self._rebuild_dag()
        self._event("rollback", f"wave {wave}")
        self._persist()
        return self._finish("rolled_back")

    def as_planner(self, spec: Mapping[str, Any]) -> dict[str, Any]:
        """Planner hook. Finished waves are not repeated."""
        if self._over_budget():
            return dict(spec)
        if not self.tasks and isinstance(spec, Mapping):
            self.spec = dict(spec)
            self._ensure_tasks()
            self._drain(None)
            self._persist()
        if not isinstance(spec, Mapping):
            return {}
        enriched = apply_plan(spec, self.artefacts)
        return enriched

    def as_qa(self, build: Mapping[str, Any]) -> dict[str, Any]:
        """QA hook. Blockers ask the builder for one ``prove_and_repair`` pass."""
        review = review_build(build if isinstance(build, Mapping) else {})
        self.latest_playtest = review
        self.issues = list(review["issues"])
        for issue in self.issues:
            if issue.get("severity") == "blocker":
                self.memory.remember("failure", str(issue.get("detail") or "qa blocker")[:500], tags=["failure", "qa"])
        ctx = ExecContext(spec=dict(self.spec), memory=self.memory, tools=self.tools)
        try:
            self.artefacts["qa"] = run_qa(ctx, review)
        except (ToolError, StudioContractError, OSError, ValueError, TypeError) as exc:
            self._event("qa", f"qa note denied: {exc}"[:200])
        blockers = any(issue.get("severity") == "blocker" for issue in self.issues)
        files = build.get("files") if isinstance(build, Mapping) else None
        if blockers and self.repairs_done < self.controls.max_repairs and isinstance(files, Mapping) and files:
            self.repairs_done += 1
            self.memory.remember("decision", "qa requested prove_and_repair", tags=["decision", "repair"])
            review = dict(review)
            review["repair_requested"] = True
            self._event("repair", "requested prove_and_repair")
        return review

    def _sanitize_brief(self) -> bool:
        if not isinstance(self.brief_text, str) or not self.brief_text.strip():
            self.brief_text = ""
            return True
        decision = self.tools.sandbox.ingest_untrusted(self.brief_text)
        if not decision.allowed:
            self.brief_text = ""
            return True
        return False

    def _ensure_tasks(self) -> None:
        if self.tasks:
            return
        from skeleton.forge.game_design_spec import compile_brief

        self.spec = compile_brief(self.brief_text) if not self.spec else self.spec
        if self.spec.get("schema_version") != "skeleton.game_design_spec.v1":
            self.spec = compile_brief(self.brief_text)
        if self.model is not None:
            self.model_calls += 1
        self.tasks = list(plan_brief(self.spec, model=self.model))
        self._rebuild_dag()

    def _rebuild_dag(self) -> None:
        self.dag = SwarmDag()
        for task in self.tasks:
            self.dag.submit(task.id, task.capability, {"goal": task.goal}, list(task.deps))
        pending = {task.id for task in self.tasks if task.id in self.artefacts}
        guard = 0
        while pending and guard < 24:
            guard += 1
            progressed = False
            for node in self.dag.ready_wave():
                if node.id not in pending:
                    continue
                claimed = self.dag.claim(node.id, "resume")
                if claimed and self.dag.complete(node.id, self.artefacts[node.id].get("id") or node.id):
                    pending.discard(node.id)
                    progressed = True
            if not progressed:
                break
        for node in self.dag._nodes.values():
            if node.status == TaskStatus.READY and node.id not in self.artefacts:
                node.status = TaskStatus.PENDING

    def _drain(self, max_waves: int | None) -> None:
        limit = self.controls.max_waves if max_waves is None else max_waves
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("max_waves must be a positive integer")
        ran = 0
        while ran < limit:
            if self._over_budget():
                self._event("budget", "planning stopped at 120s")
                break
            wave = self.dag.ready_wave()
            if not wave:
                break
            for node in wave:
                task = self._task(node.id)
                if task is None or task.id in self.artefacts:
                    continue
                self._execute(task)
            self._snapshot()
            ran += 1
            self.waves_run += 1

    def _execute(self, task: PlannedTask) -> None:
        handler = HANDLERS.get(task.capability)
        claimed = self.dag.claim(task.id, task.role.value)
        if claimed is None or handler is None:
            return
        envelope = self.handoffs.submit(task.capability, {"goal": task.goal}, requester="studio")
        self.handoffs.accept(envelope.task_id, assignee=task.role.value)
        ctx = ExecContext(spec=self.spec, memory=self.memory, tools=self.tools)
        try:
            artefact = handler(ctx)
            validate_capability_output(task.capability, artefact)
        except (ToolError, StudioContractError, OSError, ValueError, TypeError, KeyError) as exc:
            self.handoffs.fail(envelope.task_id, str(exc)[:200] or "handler failed")
            self.dag.fail(task.id)
            self.memory.remember("failure", f"{task.id} failed", tags=["failure", task.role.value])
            self._event("task", f"{task.id} failed")
            return
        self.artefacts[task.id] = dict(artefact)
        self.execution_counts[task.role.value] = self.execution_counts.get(task.role.value, 0) + 1
        self.handoffs.complete(envelope.task_id, artefacts=[{"id": str(artefact.get("id") or task.id)}])
        if not self.dag.complete(task.id, str(artefact.get("id") or task.id)):
            self.dag.fail(task.id)
        self._event("task", task.id)

    def _snapshot(self) -> None:
        files = capture_tree(self.workspace)
        hashes = store_blobs(self.workspace, files)
        self._waves.append(
            {
                "index": len(self._waves),
                "files": hashes,
                "artefacts": {key: dict(value) for key, value in self.artefacts.items()},
                "memory": self.memory.snapshot(),
                "issues": [dict(item) for item in self.issues],
                "repairs": self.repairs_done,
            }
        )
        self._event("checkpoint", f"wave {len(self._waves) - 1}")

    def _persist(self) -> None:
        if not self._waves and not self.rejected:
            files = capture_tree(self.workspace)
            hashes = store_blobs(self.workspace, files)
            self._waves.append(
                {
                    "index": 0,
                    "files": hashes,
                    "artefacts": {key: dict(value) for key, value in self.artefacts.items()},
                    "memory": self.memory.snapshot(),
                    "issues": [dict(item) for item in self.issues],
                    "repairs": self.repairs_done,
                }
            )
        manifest = {
            "schema_version": CHECKPOINT_SCHEMA,
            "run_id": self.run_id,
            "brief": self.brief_text,
            "tasks": [task.to_dict() for task in self.tasks],
            "waves": self._waves,
            "events": self.events[-200:],
        }
        save_manifest(self.workspace, manifest)

    def _load(self, data: Mapping[str, Any]) -> None:
        brief = data.get("brief")
        if isinstance(brief, str):
            self.brief_text = brief
            self.rejected = False
        self.run_id = str(data.get("run_id") or self.run_id)
        self.tasks = [PlannedTask.from_dict(item) for item in data.get("tasks") or [] if isinstance(item, Mapping)]
        waves = [dict(item) for item in data.get("waves") or [] if isinstance(item, dict)]
        self._waves = waves
        current = waves[-1] if waves else {}
        artefacts = current.get("artefacts") if isinstance(current.get("artefacts"), Mapping) else {}
        self.artefacts = {str(key): dict(value) for key, value in artefacts.items() if isinstance(value, Mapping)}
        self.issues = [dict(item) for item in current.get("issues") or [] if isinstance(item, dict)]
        repairs = current.get("repairs") or 0
        self.repairs_done = repairs if isinstance(repairs, int) and not isinstance(repairs, bool) else 0
        self.memory = ProjectMemory(self.run_id or "studio", top_k=self.controls.top_k)
        self.memory.restore(list(current.get("memory") or []))
        self.events = [dict(item) for item in data.get("events") or [] if isinstance(item, dict)]
        files = current.get("files") if isinstance(current.get("files"), Mapping) else {}
        materialize(self.workspace, {str(key): str(value) for key, value in files.items()})
        if self.tasks:
            from skeleton.forge.game_design_spec import compile_brief

            try:
                self.spec = compile_brief(self.brief_text)
            except ValueError:
                self.spec = {}
            self._rebuild_dag()
        self._phase = "resumed"
        self._event("resume", f"waves {len(self._waves)}")

    def checkpoint(self) -> dict[str, Any]:
        try:
            loaded = load_manifest(self.workspace)
        except (CheckpointError, OSError):
            loaded = {}
        return {
            "schema_version": CHECKPOINT_SCHEMA,
            "run_id": self.run_id,
            "wave": max(len(self._waves) - 1, 0),
            "waves": len(self._waves),
            "path": str(self.workspace / ".studio" / "checkpoint.json"),
            "on_disk": bool(loaded),
        }

    def _plan_complete(self) -> bool:
        return bool(self.tasks) and all(task.id in self.artefacts for task in self.tasks)

    def _over_budget(self) -> bool:
        return (self._clock() - self._started) > self.controls.budget_s

    def _status(self) -> str:
        review = self.latest_playtest or {}
        if review.get("passed") is True:
            return "completed"
        if self._build is None:
            return "failed"
        return "failed"

    def _finish(self, status: str) -> StudioReport:
        report = StudioReport(
            run_id=self.run_id,
            status=status,
            brief=self.brief_text,
            tasks=[task.to_dict() for task in self.tasks],
            artefacts={key: dict(value) for key, value in self.artefacts.items()},
            issues=[dict(item) for item in self.issues],
            playtest=dict(self.latest_playtest) if isinstance(self.latest_playtest, Mapping) else None,
            economics=self._economics(),
            events=list(self.events),
            handoffs=self.handoffs.stats(),
            checkpoint=self.checkpoint(),
            score=score_build(self._build),
            execution_counts=dict(self.execution_counts),
        )
        self._last_report = report
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
            "budget_s": self.controls.budget_s,
        }

    def _event(self, kind: str, detail: str) -> None:
        self.events.append({"kind": kind, "detail": detail, "at": self._clock()})
        if len(self.events) > 200:
            self.events = self.events[-200:]

    def _task(self, task_id: str) -> PlannedTask | None:
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None


def _brief_text(raw: str | Mapping[str, Any]) -> str:
    if isinstance(raw, str):
        return " ".join(raw.split())
    if isinstance(raw, Mapping):
        text = raw.get("brief") if isinstance(raw.get("brief"), str) else raw.get("pitch")
        return " ".join(str(text or "").split())
    raise ValueError("brief must be a string")


def _default_builder(
    brief: str,
    *,
    planner: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    qa: Callable[[Mapping[str, Any]], Mapping[str, Any]],
    playtest_mode: str,
    out: str,
) -> dict[str, Any]:
    from skeleton.forge.game_builder import build_playable_game

    return build_playable_game(
        brief,
        planner=planner,
        qa=qa,
        playtest_mode=playtest_mode,
        out=out,
        overwrite=True,
    )
