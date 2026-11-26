"""In-repo cloud-agent office for the local game studio.

The run queue is the jobs-durability record: queued, running, succeeded,
failed, or cancelled, with ordered tool steps, thoughts quoted from tool
output, heartbeats, and cancellation. Charter mandates live here. HTTP
admission stays on the forge charter in ``skeleton.api``.

Plans are deterministic. This module does not call a model provider.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from typing import Any, Callable, Mapping

from skeleton.forge.game_design_spec import GOLDEN_BRIEFS
from skeleton.forge.playtest import PLAYTEST_MODES
from skeleton.frontier.runtime.operation_stream import (
    STREAM_SCHEMA_VERSION,
    OperationEventLog,
    ReplayCursor,
    StreamContractError,
)
from skeleton.skills.studio_office_tools import default_tools

RUN_SCHEMA = "skeleton.studio_office_run.v1"
OFFICE_SCHEMA = "skeleton.studio_office.v1"
GOLDEN_BRIEF_ID = "top_down_shooter"
TERMINAL = frozenset({"succeeded", "failed", "cancelled"})
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})
_ID_MAX = 128

CHARTERS: dict[str, dict[str, Any]] = {
    "doctor": {
        "charter_id": "doctor",
        "mandate": "Inspect the install with the existing doctor and report its codes. Do not mutate the install or start a build.",
        "tools": ["doctor"],
        "autonomy": "act",
        "budget": {"max_tool_calls": 1, "deadline_s": 10},
    },
    "game_builder": {
        "charter_id": "game_builder",
        "mandate": "After a green doctor, compile the admitted brief with build_playable_game and playtest auto. Do not invent a second builder.",
        "tools": ["doctor", "game_build"],
        "autonomy": "act",
        "budget": {"max_tool_calls": 2, "deadline_s": 120},
    },
    "playtest": {
        "charter_id": "playtest",
        "mandate": "Replay the scripted playtest agent against an admitted content fixture. Do not start a build.",
        "tools": ["playtest"],
        "autonomy": "act",
        "budget": {"max_tool_calls": 1, "deadline_s": 30},
    },
    "job_watcher": {
        "charter_id": "job_watcher",
        "mandate": "Advise on one forge job and the caller's projects. Do not enqueue a build.",
        "tools": ["job_status", "list_projects"],
        "autonomy": "advise",
        "budget": {"max_tool_calls": 2, "deadline_s": 10},
    },
}


class OfficeRejected(Exception):
    """The office refused a run before or instead of doing the work."""

    def __init__(self, code: str, message: str, *, status: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class OfficeCancelled(Exception):
    """The active plan must stop because the run is already terminal."""


class _Cancel:
    def __init__(self) -> None:
        self._event = threading.Event()

    def set(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


def loopback_allowed(host: str | None) -> bool:
    """Office mutations are loopback-only unless the operator opts in."""
    if os.environ.get("SKELETON_OFFICE_ALLOW_REMOTE") == "1":
        return True
    return isinstance(host, str) and host in _LOOPBACK_HOSTS


def golden_brief() -> dict[str, str]:
    for item in GOLDEN_BRIEFS:
        if item.get("id") == GOLDEN_BRIEF_ID:
            return dict(item)
    raise OfficeRejected("golden_brief_missing", "top-down shooter golden brief is not in the forge catalog")


def list_charters() -> list[dict[str, Any]]:
    return [_public_charter(row) for row in CHARTERS.values()]


def _public_charter(row: Mapping[str, Any]) -> dict[str, Any]:
    budget = dict(row["budget"])
    return {
        "schema_version": OFFICE_SCHEMA,
        "charter_id": row["charter_id"],
        "mandate": row["mandate"],
        "tools": list(row["tools"]),
        "autonomy": row["autonomy"],
        "budget": budget,
    }


def _thought(tool: str, output: Mapping[str, Any]) -> str:
    """Quote tool fields. Never claim CORE_LOOP_OK unless the tool did."""
    if tool == "doctor":
        return f"doctor green={output.get('green')} codes={output.get('codes')}"
    if tool == "game_build":
        proved = "CORE_LOOP_OK" if output.get("core_loop_ok") is True else "godot_did_not_prove"
        return (
            f"game_build ok={output.get('ok')} {proved} godot_ran={output.get('godot_ran')} "
            f"degraded={output.get('degraded')} degraded_reason={output.get('degraded_reason')} "
            f"playtest_status={output.get('playtest_status')} code={output.get('code')}"
        )
    if tool == "playtest":
        proved = "CORE_LOOP_OK" if output.get("core_loop_ok") is True else "godot_did_not_prove"
        return (
            f"playtest code={output.get('code')} taxonomy={output.get('agent_taxonomy')} "
            f"{proved} godot_ran={output.get('godot_ran')}"
        )
    if tool == "job_status":
        return f"job_status ok={output.get('ok')} status={output.get('status')} code={output.get('code')}"
    if tool == "list_projects":
        items = output.get("items")
        count = len(items) if isinstance(items, list) else 0
        return f"list_projects ok={output.get('ok')} count={count} code={output.get('code')}"
    return f"{tool} ok={output.get('ok')} code={output.get('code')}"


def _bound(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return None
    if value is None or isinstance(value, (bool, int, float)):
        if isinstance(value, float) and value != value:
            return None
        return value
    if isinstance(value, str):
        return value[:500]
    if isinstance(value, list):
        return [_bound(item, depth=depth + 1) for item in value[:32]]
    if isinstance(value, Mapping):
        blocked = {"files", "content", "_operator", "binary"}
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:40]:
            name = str(key)[:64]
            if name in blocked:
                continue
            out[name] = _bound(item, depth=depth + 1)
        return out
    return str(value)[:120]


class OfficeQueue:
    """Process-local office runs. The forge job queue remains the build owner."""

    def __init__(
        self,
        tools: Mapping[str, Callable[..., Any]] | None = None,
        *,
        store: Callable[[Mapping[str, Any]], None] | None = None,
        recall: Callable[..., Mapping[str, Any]] | None = None,
    ) -> None:
        self._tools = dict(default_tools() if tools is None else tools)
        self._store = store
        self._recall = recall
        self._lock = threading.RLock()
        self._runs: dict[str, dict[str, Any]] = {}

    def submit(
        self,
        charter_id: str,
        *,
        actor_id: str,
        tenant_id: str,
        params: Mapping[str, Any] | None = None,
        inline: bool = False,
    ) -> dict[str, Any]:
        if charter_id not in CHARTERS:
            raise OfficeRejected("unknown_charter", "unknown office charter")
        clean = self._validate(charter_id, params or {})
        with self._lock:
            self._reap()
            active = sum(1 for run in self._runs.values() if run["status"] in {"queued", "running"})
            if active >= 8:
                raise OfficeRejected("office_busy", "office run capacity is full", status=503)
            run = self._new(charter_id, actor_id, tenant_id, clean)
            self._runs[run["run_id"]] = run
            self._emit(run, "operation.progress", {"phase": "queued", "charter_id": charter_id})
            view = self._view(run)
        if inline:
            self._execute(run["run_id"])
            return self.get(run["run_id"], actor_id=actor_id, tenant_id=tenant_id)
        threading.Thread(target=self._execute, args=(run["run_id"],), name="studio-office", daemon=True).start()
        return view

    def submit_golden(
        self,
        *,
        actor_id: str,
        tenant_id: str,
        frames: int = 4,
        live: bool = False,
        inline: bool = False,
    ) -> dict[str, Any]:
        item = golden_brief()
        if isinstance(frames, bool) or not isinstance(frames, int) or not 1 <= frames <= 64:
            raise OfficeRejected("frames_invalid", "frames must be an integer from 1 to 64")
        if live is not True and live is not False:
            raise OfficeRejected("live_invalid", "live must be a boolean")
        return self.submit(
            "game_builder",
            actor_id=actor_id,
            tenant_id=tenant_id,
            params={
                "brief": item["brief"],
                "brief_id": item["id"],
                "genre": item["genre"],
                "playtest": "auto",
                "frames": frames,
                "live": live,
            },
            inline=inline,
        )

    def get(self, run_id: str, *, actor_id: str, tenant_id: str) -> dict[str, Any]:
        with self._lock:
            try:
                run = self._owned(run_id, actor_id, tenant_id)
            except KeyError:
                run = None
            else:
                return self._view(run)
        try:
            recalled = self._load(run_id, actor_id=actor_id, tenant_id=tenant_id)
        except KeyError:
            raise
        except Exception as exc:
            raise OfficeRejected("job_unavailable", "office run record is unavailable", status=503) from exc
        if recalled.get("actor_id") != actor_id or recalled.get("tenant_id") != tenant_id:
            raise KeyError(run_id)
        return dict(recalled)

    def accept(self, run_id: str, *, actor_id: str, tenant_id: str) -> dict[str, Any]:
        """Apply an advise proposal. The builder stays idle until this call."""
        with self._lock:
            run = self._owned(run_id, actor_id, tenant_id)
            result = run.get("result") if isinstance(run.get("result"), Mapping) else {}
            proposal = result.get("proposal") if isinstance(result, Mapping) else None
            if not isinstance(proposal, Mapping) or result.get("awaiting_accept") is not True:
                raise OfficeRejected("proposal_missing", "this run has no proposal waiting for accept")
            if proposal.get("tool") != "game_build":
                raise OfficeRejected("proposal_refused", "this proposal does not apply a game build")
            run["params"]["autonomy"] = "act"
            run["params"]["brief"] = proposal.get("brief")
            run["params"]["playtest"] = proposal.get("playtest") or "auto"
            run["autonomy"] = "act"
            run["status"] = "running"
            run["status_history"].append("running")
            run["tool_calls"] = 0
            run["budget"]["tool_calls"] = 0
            run["deadline_at"] = time.monotonic() + float(CHARTERS["game_builder"]["budget"]["deadline_s"])
            run["result"] = {"proposal": dict(proposal), "awaiting_accept": False, "applied": True}
            run["error"] = None
        try:
            self._plan_game_builder(run)
        except OfficeCancelled:
            pass
        return self.get(run_id, actor_id=actor_id, tenant_id=tenant_id)

    def reject(self, run_id: str, *, actor_id: str, tenant_id: str) -> dict[str, Any]:
        """Decline an advise proposal without calling the builder."""
        with self._lock:
            run = self._owned(run_id, actor_id, tenant_id)
            result = run.get("result") if isinstance(run.get("result"), Mapping) else {}
            proposal = result.get("proposal") if isinstance(result, Mapping) else None
            if not isinstance(proposal, Mapping) or result.get("awaiting_accept") is not True:
                raise OfficeRejected("proposal_missing", "this run has no proposal waiting for reject")
            run["status"] = "running"
            self._finish(
                run,
                "failed",
                code="proposal_rejected",
                result={"proposal": dict(proposal), "awaiting_accept": False, "applied": False},
            )
            return self._view(run)

    def cancel(self, run_id: str, *, actor_id: str, tenant_id: str) -> dict[str, Any]:
        with self._lock:
            run = self._owned(run_id, actor_id, tenant_id)
            run["cancel"].set()
            waiting = isinstance(run.get("result"), Mapping) and run["result"].get("awaiting_accept") is True
            if run["status"] in {"queued", "running"} or waiting:
                if waiting and run["status"] in TERMINAL:
                    run["status"] = "running"
                self._finish(run, "cancelled", code="cancelled")
            return self._view(run)

    def replay(self, run_id: str, *, actor_id: str, tenant_id: str, after: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            run = self._owned(run_id, actor_id, tenant_id)
            try:
                events = run["stream"].replay(ReplayCursor(run["run_id"], after_sequence=after))
            except StreamContractError:
                return []
            return [event.as_dict() for event in events]

    def _validate(self, charter_id: str, params: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(params, Mapping):
            raise OfficeRejected("params_invalid", "office params must be an object")
        clean: dict[str, Any] = {}
        brief = params.get("brief")
        if brief is not None:
            if not isinstance(brief, str) or not brief.strip() or len(brief) > 4000:
                raise OfficeRejected("brief_invalid", "brief must be text up to 4000 characters")
            clean["brief"] = brief.strip()
        brief_id = params.get("brief_id")
        if brief_id is not None:
            if not isinstance(brief_id, str) or len(brief_id) > 64:
                raise OfficeRejected("brief_invalid", "brief_id is invalid")
            clean["brief_id"] = brief_id
        if "playtest" in params:
            mode = params.get("playtest")
            if mode not in PLAYTEST_MODES:
                raise OfficeRejected("playtest_invalid", "playtest must be off, auto, or require")
            clean["playtest"] = mode
        if "frames" in params:
            frames = params.get("frames")
            if isinstance(frames, bool) or not isinstance(frames, int) or not 1 <= frames <= 64:
                raise OfficeRejected("frames_invalid", "frames must be an integer from 1 to 64")
            clean["frames"] = frames
        if "live" in params:
            live = params.get("live")
            if live is not True and live is not False:
                raise OfficeRejected("live_invalid", "live must be a boolean")
            clean["live"] = live
        if "execution_id" in params:
            execution_id = params.get("execution_id")
            if not isinstance(execution_id, str) or not execution_id or len(execution_id) > _ID_MAX:
                raise OfficeRejected("execution_invalid", "execution_id must be a short identifier")
            clean["execution_id"] = execution_id
        if "genre" in params:
            genre = params.get("genre")
            if not isinstance(genre, str) or not genre or len(genre) > 64:
                raise OfficeRejected("genre_invalid", "genre must be a short string")
            clean["genre"] = genre
        if "content" in params:
            content = params.get("content")
            if not isinstance(content, Mapping):
                raise OfficeRejected("content_invalid", "content must be an object")
            import json
            encoded = json.dumps(content, default=str)
            if len(encoded.encode("utf-8")) > 65536:
                raise OfficeRejected("content_invalid", "content exceeds 64 KiB")
            clean["content"] = content
        if "require_godot" in params:
            flag = params.get("require_godot")
            if flag is not True and flag is not False:
                raise OfficeRejected("playtest_invalid", "require_godot must be a boolean")
            clean["require_godot"] = flag
        if "autonomy" in params:
            autonomy = params.get("autonomy")
            if autonomy not in {"act", "advise"}:
                raise OfficeRejected("autonomy_invalid", "autonomy must be act or advise")
            clean["autonomy"] = autonomy
        if charter_id == "job_watcher" and ("brief" in clean or clean.get("playtest") not in (None, "off")):
            clean["refused_mutation"] = True
        return clean

    def _new(self, charter_id: str, actor_id: str, tenant_id: str, params: Mapping[str, Any]) -> dict[str, Any]:
        charter = CHARTERS[charter_id]
        now = time.time()
        run_id = str(uuid.uuid4())
        deadline_s = float(charter["budget"]["deadline_s"])
        return {
            "schema_version": RUN_SCHEMA,
            "run_id": run_id,
            "charter_id": charter_id,
            "mandate": charter["mandate"],
            "tools": list(charter["tools"]),
            "autonomy": charter["autonomy"],
            "budget": {"max_tool_calls": charter["budget"]["max_tool_calls"], "deadline_s": deadline_s, "tool_calls": 0},
            "actor_id": actor_id,
            "tenant_id": tenant_id,
            "params": dict(params),
            "status": "queued",
            "status_history": ["queued"],
            "created_at": now,
            "updated_at": now,
            "heartbeat_at": now,
            "heartbeat_seq": 0,
            "deadline_at": time.monotonic() + deadline_s,
            "steps": [],
            "result": None,
            "error": None,
            "cancel": _Cancel(),
            "stream": OperationEventLog(run_id, capacity=256),
            "stream_schema": STREAM_SCHEMA_VERSION,
            "stream_error": None,
            "tool_calls": 0,
        }

    def _execute(self, run_id: str) -> None:
        with self._lock:
            run = self._runs[run_id]
            if run["cancel"].cancelled or run["status"] in TERMINAL:
                self._finish(run, "cancelled", code="cancelled")
                return
            self._transition(run, "running")
        stop = threading.Event()

        def beat() -> None:
            while not stop.wait(0.05):
                with self._lock:
                    if run["status"] == "running":
                        self._beat(run)

        thread = threading.Thread(target=beat, name="office-heartbeat", daemon=True)
        thread.start()
        try:
            self._plan(run)
        except OfficeCancelled:
            pass
        except Exception as exc:
            with self._lock:
                self._finish(run, "failed", code="office_failed", result={"error": type(exc).__name__})
        finally:
            stop.set()
            thread.join(timeout=0.2)

    def _plan(self, run: dict[str, Any]) -> None:
        charter_id = run["charter_id"]
        if charter_id == "doctor":
            self._plan_doctor(run)
        elif charter_id == "game_builder":
            self._plan_game_builder(run)
        elif charter_id == "playtest":
            self._plan_playtest(run)
        elif charter_id == "job_watcher":
            self._plan_watcher(run)
        else:
            with self._lock:
                self._finish(run, "failed", code="unknown_charter")

    def _plan_doctor(self, run: dict[str, Any]) -> None:
        output = self._tool(run, "doctor", live=bool(run["params"].get("live", False)))
        if output.get("ok") is False:
            self._fail(run, str(output.get("code") or "doctor_unavailable"), output)
            return
        self._succeed(run, {"green": output.get("green"), "codes": output.get("codes")})

    def _plan_game_builder(self, run: dict[str, Any]) -> None:
        if not run["params"].get("brief"):
            self._fail(run, "brief_required", {"ok": False, "code": "brief_required"})
            return
        if run["params"].get("autonomy") == "advise":
            self._succeed(run, {
                "proposal": {
                    "tool": "game_build",
                    "brief": run["params"]["brief"],
                    "playtest": run["params"].get("playtest") or "auto",
                    "charter_id": "game_builder",
                },
                "awaiting_accept": True,
                "applied": False,
            })
            return
        doctor = self._tool(run, "doctor", live=bool(run["params"].get("live", False)))
        if doctor.get("ok") is False or doctor.get("green") is not True:
            self._fail(run, "doctor_red", {
                "ok": False,
                "code": "doctor_red",
                "codes": doctor.get("codes"),
                "services_ready": doctor.get("services_ready"),
            })
            return
        remaining = max(0.05, run["deadline_at"] - time.monotonic())
        built = self._tool(
            run,
            "game_build",
            brief=run["params"]["brief"],
            playtest=run["params"].get("playtest") or "auto",
            deadline_s=min(120.0, remaining),
        )
        if built.get("ok") is not True:
            self._fail(run, str(built.get("code") or "game_build_failed"), built)
            return
        payload = dict(built)
        if run["params"].get("brief_id"):
            payload["brief_id"] = run["params"]["brief_id"]
        prior = run.get("result") if isinstance(run.get("result"), Mapping) else {}
        if isinstance(prior.get("proposal"), Mapping):
            payload["proposal"] = dict(prior["proposal"])
            payload["applied"] = True
            payload["awaiting_accept"] = False
        self._succeed(run, payload)

    def _plan_playtest(self, run: dict[str, Any]) -> None:
        if run["params"].get("brief"):
            self._fail(run, "playtest_refuses_builder", {"ok": False, "code": "playtest_refuses_builder"})
            return
        if "content" not in run["params"] or "genre" not in run["params"]:
            self._fail(run, "playtest_input_missing", {"ok": False, "code": "playtest_input_missing"})
            return
        require = run["params"].get("playtest") == "require" or run["params"].get("require_godot") is True
        output = self._tool(
            run,
            "playtest",
            genre=run["params"]["genre"],
            content=run["params"]["content"],
            frames=int(run["params"].get("frames") or 4),
            require_godot=require,
        )
        if output.get("ok") is not True:
            self._fail(run, str(output.get("code") or "playtest_failed"), output)
            return
        self._succeed(run, output)

    def _plan_watcher(self, run: dict[str, Any]) -> None:
        if run["params"].get("refused_mutation"):
            self._fail(run, "autonomy_advise", {"ok": False, "code": "autonomy_advise"})
            return
        if not run["params"].get("execution_id"):
            self._fail(run, "execution_required", {"ok": False, "code": "execution_required"})
            return
        status = self._tool(run, "job_status", execution_id=run["params"]["execution_id"])
        projects = self._tool(run, "list_projects")
        if status.get("ok") is not True:
            self._fail(run, str(status.get("code") or "job_unavailable"), {"job": status, "projects": projects})
            return
        if projects.get("ok") is not True:
            self._fail(run, str(projects.get("code") or "projects_unavailable"), {"job": status, "projects": projects})
            return
        self._succeed(run, {"job": status, "projects": projects})

    def _tool(self, run: dict[str, Any], name: str, **kwargs: Any) -> dict[str, Any]:
        with self._lock:
            if run["status"] in TERMINAL:
                raise OfficeCancelled()
            if run["cancel"].cancelled:
                self._finish(run, "cancelled", code="cancelled")
                raise OfficeCancelled()
            charter = CHARTERS[run["charter_id"]]
            if name not in charter["tools"]:
                self._finish(run, "failed", code="tool_forbidden", result={"tool": name})
                raise OfficeCancelled()
            if run["tool_calls"] >= int(charter["budget"]["max_tool_calls"]):
                self._finish(run, "failed", code="budget_exhausted")
                raise OfficeCancelled()
            if time.monotonic() >= run["deadline_at"]:
                self._finish(run, "failed", code="deadline_exceeded")
                raise OfficeCancelled()
            run["tool_calls"] += 1
            run["budget"]["tool_calls"] = run["tool_calls"]
            index = len(run["steps"])
            run["steps"].append({
                "index": index,
                "tool": name,
                "status": "running",
                "thought": "",
                "output": {},
                "started_at": time.time(),
                "finished_at": None,
            })
            self._beat(run)
            self._emit(run, "operation.progress", {"tool": name, "phase": "started", "index": index})
        fn = self._tools.get(name)
        if fn is None:
            output: Any = {"ok": False, "code": "tool_missing"}
        else:
            try:
                output = fn(
                    actor_id=run["actor_id"],
                    tenant_id=run["tenant_id"],
                    on_progress=lambda fraction, message, step_index=index: self._note(run, step_index, fraction, message),
                    **kwargs,
                )
            except OfficeCancelled:
                raise
            except Exception as exc:
                output = {"ok": False, "code": "tool_failed", "error": type(exc).__name__}
        if not isinstance(output, Mapping):
            output = {"ok": False, "code": "tool_output_invalid"}
        bounded = _bound(dict(output))
        if not isinstance(bounded, dict):
            bounded = {"ok": False, "code": "tool_output_invalid"}
        thought = _thought(name, bounded)
        with self._lock:
            step = run["steps"][index]
            if run["cancel"].cancelled or run["status"] == "cancelled":
                step["status"] = "cancelled"
            elif bounded.get("ok") is False:
                step["status"] = "failed"
            else:
                step["status"] = "succeeded"
            step["output"] = bounded
            step["thought"] = thought
            step["finished_at"] = time.time()
            self._beat(run)
            if run["status"] not in TERMINAL:
                self._emit(run, "operation.progress", {
                    "tool": name,
                    "phase": "finished",
                    "index": index,
                    "thought": thought,
                    "ok": bounded.get("ok"),
                    "code": bounded.get("code"),
                })
            if run["status"] in TERMINAL or run["cancel"].cancelled:
                if run["status"] not in TERMINAL:
                    self._finish(run, "cancelled", code="cancelled")
                raise OfficeCancelled()
        return bounded

    def _note(self, run: dict[str, Any], index: int, fraction: float, message: str) -> None:
        text = str(message or "")[:160]
        with self._lock:
            if run["status"] != "running" or index >= len(run["steps"]):
                return
            step = run["steps"][index]
            previous = step["output"].get("progress_message") if isinstance(step["output"], dict) else None
            if not isinstance(step["output"], dict):
                step["output"] = {}
            step["output"]["progress"] = fraction if isinstance(fraction, (int, float)) else None
            step["output"]["progress_message"] = text
            self._beat(run)
            if previous != text and text:
                self._emit(run, "operation.progress", {"tool": step["tool"], "phase": "progress", "index": index, "message": text})

    def _succeed(self, run: dict[str, Any], result: Mapping[str, Any]) -> None:
        with self._lock:
            self._finish(run, "succeeded", result=dict(result))

    def _fail(self, run: dict[str, Any], code: str, result: Mapping[str, Any]) -> None:
        with self._lock:
            self._finish(run, "failed", code=code, result=dict(result))

    def _finish(self, run: dict[str, Any], status: str, *, code: str | None = None, result: Mapping[str, Any] | None = None) -> None:
        if run["status"] in TERMINAL:
            return
        self._transition(run, status)
        payload = _bound(dict(result or {}))
        if not isinstance(payload, dict):
            payload = {}
        if status == "succeeded":
            run["result"] = payload
            run["error"] = None
            event = "operation.completed"
        elif status == "cancelled":
            run["result"] = None
            run["error"] = {"code": "cancelled"}
            event = "operation.cancelled"
        else:
            run["result"] = payload or None
            run["error"] = {"code": code or "failed"}
            event = "operation.failed"
        self._beat(run)
        self._emit(run, event, {"status": status, "code": (run.get("error") or {}).get("code") if isinstance(run.get("error"), dict) else None})
        if run["error"] is None or (isinstance(run.get("error"), dict) and run["error"].get("code") != "job_unavailable"):
            try:
                self._persist(run)
            except Exception:
                run["status"] = "failed"
                if "failed" not in run["status_history"]:
                    run["status_history"].append("failed")
                run["result"] = None
                run["error"] = {"code": "job_unavailable"}

    def _transition(self, run: dict[str, Any], status: str) -> None:
        run["status"] = status
        run["status_history"].append(status)
        run["updated_at"] = time.time()

    def _beat(self, run: dict[str, Any]) -> None:
        run["heartbeat_seq"] = int(run["heartbeat_seq"]) + 1
        run["heartbeat_at"] = time.time()
        run["updated_at"] = run["heartbeat_at"]

    def _emit(self, run: dict[str, Any], event_type: str, payload: Mapping[str, Any]) -> None:
        try:
            run["stream"].append(event_type, _bound(dict(payload)) or {})
        except StreamContractError as exc:
            run["stream_error"] = type(exc).__name__

    def _persist(self, run: Mapping[str, Any]) -> None:
        view = self._view(run)
        if self._store is not None:
            self._store(view)
            return
        from skeleton.forge.game_build_queue import remember_office_run

        remember_office_run(view)

    def _load(self, run_id: str, *, actor_id: str, tenant_id: str) -> Mapping[str, Any]:
        if self._recall is not None:
            loaded = self._recall(run_id, actor_id=actor_id, tenant_id=tenant_id)
        else:
            from skeleton.forge.game_build_queue import recall_office_run

            loaded = recall_office_run(run_id, actor_id=actor_id, tenant_id=tenant_id)
        if not isinstance(loaded, Mapping):
            raise KeyError(run_id)
        return loaded

    def _owned(self, run_id: str, actor_id: str, tenant_id: str) -> dict[str, Any]:
        run = self._runs.get(run_id)
        if run is None or run["actor_id"] != actor_id or run["tenant_id"] != tenant_id:
            raise KeyError(run_id)
        return run

    def _reap(self) -> None:
        if len(self._runs) < 32:
            return
        finished = [run_id for run_id, run in self._runs.items() if run["status"] in TERMINAL]
        for run_id in finished[: len(self._runs) - 24]:
            self._runs.pop(run_id, None)

    def _view(self, run: Mapping[str, Any]) -> dict[str, Any]:
        steps = []
        for step in run["steps"]:
            steps.append({
                "index": step["index"],
                "tool": step["tool"],
                "status": step["status"],
                "thought": step["thought"],
                "output": step["output"],
                "started_at": step["started_at"],
                "finished_at": step["finished_at"],
            })
        return {
            "schema_version": RUN_SCHEMA,
            "run_id": run["run_id"],
            "charter_id": run["charter_id"],
            "mandate": run["mandate"],
            "tools": list(run["tools"]),
            "autonomy": run["autonomy"],
            "budget": dict(run["budget"]),
            "actor_id": run["actor_id"],
            "tenant_id": run["tenant_id"],
            "status": run["status"],
            "status_history": list(run["status_history"]),
            "created_at": run["created_at"],
            "updated_at": run["updated_at"],
            "heartbeat_at": run["heartbeat_at"],
            "heartbeat_seq": run["heartbeat_seq"],
            "steps": steps,
            "result": run["result"],
            "error": run["error"],
            "stream_error": run["stream_error"],
            "brief_id": run["params"].get("brief_id"),
            "playtest": run["params"].get("playtest"),
            "status_ref": f"/api/v1/game/office/runs/{run['run_id']}",
            "stream_ref": f"/api/v1/game/office/runs/{run['run_id']}/stream",
        }


_office: OfficeQueue | None = None
_office_lock = threading.Lock()


def get_office() -> OfficeQueue:
    global _office
    with _office_lock:
        if _office is None:
            _office = OfficeQueue()
        return _office


def reset_office(queue: OfficeQueue | None = None) -> OfficeQueue:
    """Test hook. Production calls use ``get_office``."""
    global _office
    with _office_lock:
        _office = queue if queue is not None else OfficeQueue()
        return _office


__all__ = [
    "CHARTERS",
    "GOLDEN_BRIEF_ID",
    "OFFICE_SCHEMA",
    "RUN_SCHEMA",
    "TERMINAL",
    "OfficeCancelled",
    "OfficeQueue",
    "OfficeRejected",
    "get_office",
    "golden_brief",
    "list_charters",
    "loopback_allowed",
    "reset_office",
]
