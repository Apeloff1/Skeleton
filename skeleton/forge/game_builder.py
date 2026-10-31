"""Brief → playable Godot project.

One entry point over the existing GameForge run, era/room materialiser,
static GDScript checker, forge repair pass, and headless Godot playtest.
The design spec and content bundle are committed by this module; Godot is
the engine target. Repair reads checker and engine errors and retries a
bounded number of times.

``planner`` and ``qa`` are the Milestone C callables (#4118). The default is
a no-op. A planner may enrich ``skeleton.game_design_spec.v1`` without
changing the committed genre, engine, brief, or scope. QA reviews the
checker, core loop, and Godot playtest. When QA sets ``repair_requested``,
this function runs one more ``prove_and_repair`` pass, and only when the
build deadline still has time left. Hooks do not materialise a second project.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import threading
import time
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence

from skeleton.forge.game_content import CONTENT_SCHEMA, generate_content
from skeleton.forge.game_design_spec import SCHEMA_VERSION, compile_brief
from skeleton.forge.genre_project import (
    CORE_LOOP_PATH,
    attach_genre,
    execute_core_loop,
    loop_succeeded,
    proof_line,
)
from skeleton.forge.playtest import normalise_mode, playtest

RUN_SCHEMA = "skeleton.game_builder_run.v1"
PROJECTS_SCHEMA = "skeleton.projects.v1"
DEFAULT_DEADLINE_S = 120.0
MAX_INLINE_FILE_BYTES = 8 * 1024 * 1024
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_UNSET = object()
_BRIEF_FIELDS = {"title", "summary", "genre", "constraints", "schema_version"}
# Frozen result contract consumed by Projects and the SDK. ``files`` is optional
# and omitted when the inline body would exceed ``MAX_INLINE_FILE_BYTES``.
RESULT_FIELDS = (
    "schema_version",
    "ok",
    "spec",
    "content_schema",
    "content",
    "marker",
    "proof",
    "check",
    "core_loop",
    "playtest",
    "repair",
    "pipeline",
    "project",
    "file_names",
    "stubbed",
    "actor_id",
    "tenant_id",
    "execution_id",
    "project_id",
    "qa",
    "deadline_s",
    "structured_brief",
)
STUBBED = (
    "authored sprites, meshes, and audio",
    "input-driven play beyond the headless core-loop proof",
    "multiplayer, persistence past the economy ledger, and store packaging",
    "provider model proposals; the deterministic compiler is the commit authority",
    "vehicle dynamics past one kinematic integration proof",
)

_SCRIPT_FAULTS = (
    "unbalanced",
    "no extends",
    "parse error",
    "script error",
    "core loop",
    "core_loop",
    "autoload",
    "required ",
    "missing file",
    "empty file",
)


def _failed_stages(payload: Mapping[str, Any]) -> list[str]:
    stages = ((payload.get("run") or {}).get("stages") if isinstance(payload.get("run"), Mapping) else None) or []
    lines = []
    for stage in stages:
        if isinstance(stage, Mapping) and stage.get("status") == "FAILED":
            lines.append(f"{stage.get('name')}: {stage.get('error') or stage.get('gate_failure') or 'failed'}")
    return lines


def _playtest_errors(report: Mapping[str, Any]) -> list[str]:
    errors = [str(item) for item in (report.get("errors") or [])]
    reason = report.get("reason") or report.get("status")
    if report.get("status") == "unavailable":
        errors.append(f"missing-godot-binary: {reason}")
    elif not report.get("passed"):
        errors.append(f"playtest {report.get('status')}")
    return errors


def _log_text(report: Mapping[str, Any] | None) -> str:
    if not isinstance(report, Mapping):
        return ""
    chunks = []
    for step in report.get("steps") or []:
        if isinstance(step, Mapping):
            chunks.append(str(step.get("log_tail") or ""))
    return "\n".join(chunks)


def read_and_repair(
    files: Mapping[str, str],
    errors: Sequence[str],
    spec: Mapping[str, Any],
    content: Mapping[str, Any],
    *,
    pack: Mapping[str, Any] | None = None,
    root=None,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Read a failure report and apply one bounded repair.

    A missing Godot binary is not a project defect, so it is not rewritten.
    Script and project-closure failures restore the canonical core loop after
    the existing forge repair pass, which owns the extraction scaffold.
    """
    blob = "\n".join(str(item) for item in errors)
    lowered = blob.lower()
    if "missing-godot-binary" in lowered and not any(token in lowered for token in _SCRIPT_FAULTS):
        return dict(files), []
    actions: list[dict[str, Any]] = []
    out = dict(files)
    if any(token in lowered for token in _SCRIPT_FAULTS):
        from skeleton.forge.repair import attempt_repair

        repaired = attempt_repair(
            out,
            request=str(spec.get("brief") or "game builder repair"),
            mode="apply",
            pack=pack,
            root=root,
        )
        repaired_files = repaired.get("files")
        if isinstance(repaired_files, Mapping):
            out = {str(key): str(value) for key, value in repaired_files.items()}
        if repaired.get("changed"):
            actions.append({
                "action": "forge_attempt_repair",
                "changed": int(repaired.get("changed") or 0),
                "read": blob[:500],
            })
    before_loop = out.get(CORE_LOOP_PATH)
    before_project = out.get("project.godot")
    out = attach_genre(out, spec, content)
    if out.get(CORE_LOOP_PATH) != before_loop or out.get("project.godot") != before_project:
        actions.append({"action": "restore_core_loop", "read": blob[:500]})
    if out == dict(files):
        return out, []
    return out, actions


def prove_and_repair(
    files: Mapping[str, str],
    spec: Mapping[str, Any],
    content: Mapping[str, Any],
    *,
    playtest_mode: str = "off",
    max_rounds: int = 3,
    pack: Mapping[str, Any] | None = None,
    binary: str | None = None,
    root=None,
    deadline_s: float | None = None,
    on_progress: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """Check, execute the core loop, boot Godot when requested, and repair.

    ``deadline_s`` is one budget for every round. ``None`` keeps the historical
    unbounded repair path. ``0`` fails before Godot. Each playtest step receives
    only the time still left.
    """
    from skeleton.forge.gdscript_check import check_files

    mode = normalise_mode(playtest_mode)
    if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or not 1 <= max_rounds <= 3:
        raise ValueError("max_rounds must be an integer from 1 to 3")
    if deadline_s is not None and (isinstance(deadline_s, bool) or not isinstance(deadline_s, (int, float))):
        raise ValueError("deadline_s must be a number of seconds")
    deadline = None if deadline_s is None else time.monotonic() + float(deadline_s)
    current = dict(files)
    actions: list[dict[str, Any]] = []
    problems: list[str] = []
    report: dict[str, Any] | None = None
    marker = ""
    rounds = 0
    ok = False
    genre = str(spec.get("genre") or "")
    if deadline is not None and time.monotonic() >= deadline:
        problems = ["deadline exceeded"]
    while rounds < max_rounds and "deadline exceeded" not in problems:
        rounds += 1
        if on_progress is not None:
            on_progress(min(0.9, 0.45 + 0.1 * rounds), f"prove round {rounds}")
        if deadline is not None and time.monotonic() >= deadline:
            problems = ["deadline exceeded"]
            break
        problems = check_files(current)
        marker = execute_core_loop(content, genre)
        errors = list(problems)
        if not loop_succeeded(marker):
            errors.append(f"core loop marker {marker!r}")
        report = None
        if not errors and mode != "off":
            report = playtest(current, binary=binary, frames=20, timeout=90, deadline=deadline)
            log = _log_text(report)
            line = proof_line(genre, marker)
            if report.get("status") == "unavailable" and mode == "auto":
                errors = []
            else:
                errors.extend(_playtest_errors(report))
                if report.get("passed") and line not in log:
                    errors.append("core loop marker missing from godot log")
                    report = dict(report)
                    report["passed"] = False
                    report["status"] = "failed"
        if not errors:
            ok = True
            break
        if rounds >= max_rounds:
            break
        if any(item.startswith("missing-godot-binary") for item in errors) and not problems:
            break
        if deadline is not None and time.monotonic() >= deadline:
            problems = ["deadline exceeded"]
            break
        revised, planned = read_and_repair(current, errors, spec, content, pack=pack, root=root)
        if not planned:
            break
        actions.extend(planned)
        current = revised
    return {
        "ok": ok,
        "files": current,
        "marker": marker,
        "proof": proof_line(genre, marker) if marker else "",
        "check": {"ok": not problems, "problems": problems[:12]},
        "core_loop": {"passed": loop_succeeded(marker), "marker": marker},
        "playtest": report,
        "repair": {"rounds": rounds, "actions": actions},
    }


_LOCKED_SPEC_FIELDS = ("schema_version", "version", "genre", "engine", "brief", "scope")


class PlannerHook(Protocol):
    """Enrich a design spec. The compiler remains the commit authority."""

    def __call__(self, spec: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return the spec to commit, or a rejected proposal the compiler ignores."""


class QaHook(Protocol):
    """Review a proved build. May set ``repair_requested`` for one more proof pass."""

    def __call__(self, build: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return issues against checker, core-loop, and playtest evidence."""


def _seal_spec(body: Mapping[str, Any]) -> dict[str, Any]:
    sealed = {key: value for key, value in body.items() if key != "spec_id"}
    encoded = json.dumps(sealed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    sealed["spec_id"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return sealed


def _expired(deadline_at: float | None) -> bool:
    return deadline_at is not None and time.monotonic() >= deadline_at


def _remaining(deadline_at: float | None) -> float | None:
    if deadline_at is None:
        return None
    return deadline_at - time.monotonic()


def _call_bounded(deadline_at: float | None, fn: Callable[..., Any], *args: Any) -> Any:
    """Run ``fn`` and stop waiting when the build deadline is reached.

    A slow planner or QA hook cannot extend the budget. The worker thread is
    abandoned at the deadline; ``TimeoutError`` tells the caller to halt.
    """
    if deadline_at is None:
        return fn(*args)
    remaining = _remaining(deadline_at)
    if remaining is None or remaining <= 0:
        raise TimeoutError("deadline exceeded")
    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["value"] = fn(*args)
        except BaseException as exc:  # noqa: BLE001 — surfaced on the caller thread
            box["error"] = exc

    worker = threading.Thread(target=run, name="game-builder-deadline", daemon=True)
    worker.start()
    worker.join(remaining)
    if worker.is_alive():
        raise TimeoutError("deadline exceeded")
    if "error" in box:
        raise box["error"]
    return box.get("value")


def _deadline_halt(
    on_progress: Callable[[float, str], None] | None,
    identity: Mapping[str, Any],
    *,
    pipeline: Mapping[str, Any] | None = None,
    spec: Mapping[str, Any] | None = None,
    content: Any = None,
    proved: Mapping[str, Any] | None = None,
    files: Mapping[str, str] | None = None,
    qa: QaHook | None = None,
    qa_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Stop the build. Later stages, repair passes, and hooks are not entered."""
    _progress(on_progress, 1.0, "deadline exceeded")
    proved = proved or {}
    proved_files = files if files is not None else proved.get("files")
    if not isinstance(proved_files, Mapping):
        proved_files = {}
    check = proved.get("check") if isinstance(proved.get("check"), Mapping) else {}
    problems = [str(item) for item in (check.get("problems") or [])]
    if "deadline exceeded" not in problems:
        problems.insert(0, "deadline exceeded")
    pipe = None
    operator = None
    if isinstance(pipeline, Mapping):
        operator = dict(pipeline)
        sim = pipeline.get("sim") if isinstance(pipeline.get("sim"), Mapping) else {}
        pipe = {
            "succeeded": bool(pipeline.get("succeeded")),
            "era": pipeline.get("era"),
            "sim_passed": bool(sim.get("passed")),
        }
    body = _blank_result(
        ok=False,
        error="deadline exceeded",
        spec=dict(spec) if isinstance(spec, Mapping) else None,
        content=content,
        marker=proved.get("marker") or "",
        proof=proved.get("proof") or "",
        check={"ok": False, "problems": problems[:12]},
        core_loop=proved.get("core_loop") or {"passed": False, "marker": ""},
        playtest=proved.get("playtest"),
        repair=proved.get("repair") or {"rounds": 0, "actions": []},
        pipeline=pipe,
        file_names=sorted(str(name) for name in proved_files),
        files={str(key): str(value) for key, value in proved_files.items()},
        _operator=operator,
        **dict(identity),
    )
    if qa is not None and qa_report is not None:
        return _attach_qa(body, qa, qa_report)
    return body


def _proof_stopped(proved: Mapping[str, Any], deadline_at: float | None) -> bool:
    problems = (proved.get("check") or {}).get("problems") or []
    return _expired(deadline_at) or "deadline exceeded" in problems


def _apply_planner(
    spec: Mapping[str, Any],
    planner: PlannerHook | None,
    *,
    deadline_at: float | None = None,
) -> dict[str, Any]:
    """Keep the compiled spec when a hook is missing or proposes a different game."""
    committed = dict(spec)
    if planner is None:
        return committed
    try:
        proposed = _call_bounded(deadline_at, planner, dict(committed))
    except TimeoutError:
        raise
    except Exception:  # noqa: BLE001 — a planner hook must not take down the build
        return committed
    if not isinstance(proposed, Mapping):
        return committed
    if any(proposed.get(key) != committed.get(key) for key in _LOCKED_SPEC_FIELDS):
        return committed
    enriched = dict(committed)
    for key, limit in (("title", 48), ("fantasy", 180), ("core_loop", 180)):
        value = proposed.get(key)
        if isinstance(value, str) and value.strip():
            enriched[key] = " ".join(value.split())[:limit].strip()
    production = proposed.get("production")
    if production is None:
        enriched.pop("production", None)
    elif isinstance(production, Mapping):
        notes: dict[str, str] = {}
        for raw_key, raw_value in list(production.items())[:12]:
            if not isinstance(raw_key, str) or not isinstance(raw_value, str):
                continue
            key = raw_key.strip()[:32]
            value = " ".join(raw_value.split())[:240].strip()
            if key and value:
                notes[key] = value
        if notes:
            enriched["production"] = notes
        else:
            enriched.pop("production", None)
    else:
        return committed
    return _seal_spec(enriched)


def _qa_view(proved: Mapping[str, Any], spec: Mapping[str, Any], content: Any) -> dict[str, Any]:
    files = proved.get("files") if isinstance(proved.get("files"), Mapping) else {}
    return {
        "ok": bool(proved.get("ok")),
        "spec": dict(spec),
        "content": content,
        "marker": proved.get("marker"),
        "proof": proved.get("proof"),
        "check": proved.get("check"),
        "core_loop": proved.get("core_loop"),
        "playtest": proved.get("playtest"),
        "repair": proved.get("repair"),
        "files": dict(files),
        "file_names": sorted(str(name) for name in files),
    }


def _call_qa(
    qa: QaHook | None,
    view: Mapping[str, Any],
    *,
    deadline_at: float | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    if qa is None:
        return None, False
    try:
        review = _call_bounded(deadline_at, qa, dict(view))
    except TimeoutError:
        return {
            "passed": False,
            "issues": [{"severity": "blocker", "source": "qa", "detail": "deadline exceeded"}],
        }, False
    except Exception:  # noqa: BLE001 — a QA hook must not take down the build
        return {
            "passed": False,
            "issues": [{"severity": "blocker", "source": "qa", "detail": "qa hook failed"}],
        }, False
    if not isinstance(review, Mapping):
        return None, False
    requested = review.get("repair_requested") is True
    stored = {key: value for key, value in review.items() if key != "repair_requested"}
    return stored, requested


def _attach_qa(body: dict[str, Any], qa: QaHook | None, report: Mapping[str, Any] | None) -> dict[str, Any]:
    if qa is not None:
        body["qa"] = dict(report) if isinstance(report, Mapping) else None
    return body


def cortex_planner_hook(cortex: Any) -> PlannerHook:
    """Return a `PlannerHook` backed by `JeevesCortex.plan_game_spec`."""
    def _hook(spec: Mapping[str, Any]) -> Mapping[str, Any]:
        if cortex is not None and hasattr(cortex, "plan_game_spec"):
            return cortex.plan_game_spec(dict(spec))
        return dict(spec)
    return _hook


def cortex_qa_hook(cortex: Any, *, learn: bool = True) -> QaHook:
    """Return a `QaHook` backed by `JeevesCortex.review_game_build` and optional online learning."""
    def _hook(build: Mapping[str, Any]) -> Mapping[str, Any]:
        if cortex is None or not hasattr(cortex, "review_game_build"):
            return {"passed": bool(build.get("ok")), "issues": []}
        verdict = dict(cortex.review_game_build(dict(build)))
        if learn and hasattr(cortex, "learn_from_game_build"):
            verdict["learning"] = cortex.learn_from_game_build(dict(build))
        return verdict
    return _hook


def finetuned_game_creation_hooks(
    cortex: Any = None,
    *,
    finetune_rounds: int = 1,
    learn_on_qa: bool = True,
) -> tuple[PlannerHook, QaHook, Any]:
    """Build or finetune a `JeevesCortex` and return `(planner_hook, qa_hook, cortex)`."""
    if cortex is None:
        from skeleton.cortex.neocortex import JeevesCortex
        cortex = JeevesCortex()
    if finetune_rounds > 0 and hasattr(cortex, "apply_gaming_weights"):
        cortex.apply_gaming_weights(rounds=finetune_rounds)
    return (
        cortex_planner_hook(cortex),
        cortex_qa_hook(cortex, learn=learn_on_qa),
        cortex,
    )


def _optional_id(value: str | None, name: str) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or _ID.fullmatch(value) is None:
        raise ValueError(f"{name} must be a projects identifier")
    return value


def coerce_brief(brief: str | Mapping[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """Accept a string or a ``skeleton.projects.v1`` brief object.

    Actor and tenant are not brief fields. They are separate arguments on
    ``build_playable_game``. Unknown object fields are rejected.
    """
    if isinstance(brief, str):
        return None, brief
    if not isinstance(brief, Mapping):
        raise ValueError("brief must be a string or a skeleton.projects.v1 object")
    unknown = sorted(set(brief) - _BRIEF_FIELDS)
    if unknown:
        raise ValueError(f"unknown brief fields: {', '.join(unknown)}")
    schema = brief.get("schema_version", PROJECTS_SCHEMA)
    if schema != PROJECTS_SCHEMA:
        raise ValueError("brief schema_version must be skeleton.projects.v1")
    title = brief.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("structured brief title is required")
    summary = brief.get("summary", "")
    genre = brief.get("genre", "")
    constraints = brief.get("constraints", [])
    if not isinstance(summary, str):
        raise ValueError("summary must be a string")
    if not isinstance(genre, str):
        raise ValueError("genre must be a string")
    if not isinstance(constraints, list) or any(not isinstance(item, str) for item in constraints):
        raise ValueError("constraints must be a list of strings")
    parts = [title.strip()]
    if summary.strip():
        parts.append(summary.strip())
    if genre.strip():
        parts.append(f"Genre: {genre.strip()}.")
    if constraints:
        parts.append("Constraints: " + "; ".join(constraints))
    structured = {
        "schema_version": PROJECTS_SCHEMA,
        "title": title.strip(),
        "summary": summary.strip(),
        "genre": genre.strip(),
        "constraints": list(constraints),
    }
    return structured, " ".join(parts)


def _blank_result(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": RUN_SCHEMA,
        "ok": False,
        "spec": None,
        "content_schema": CONTENT_SCHEMA,
        "content": None,
        "marker": "",
        "proof": "",
        "check": None,
        "core_loop": None,
        "playtest": None,
        "repair": None,
        "pipeline": None,
        "project": None,
        "file_names": [],
        "files": {},
        "stubbed": list(STUBBED),
        "actor_id": None,
        "tenant_id": None,
        "execution_id": None,
        "project_id": None,
        "deadline_s": DEFAULT_DEADLINE_S,
        "structured_brief": None,
    }
    body.update(overrides)
    return body


def _progress(callback: Callable[[float, str], None] | None, fraction: float, message: str) -> None:
    if callback is not None:
        callback(fraction, message)


def _resolved_brief_text(supplied: str, pipeline: Mapping[str, Any]) -> str:
    if supplied.strip():
        return supplied.strip()
    intake = pipeline.get("intake") if isinstance(pipeline.get("intake"), Mapping) else {}
    vision = str((intake or {}).get("vision") or "").strip()
    if vision:
        return vision
    era = str(pipeline.get("era") or "").strip()
    return era or "playable game"


def build_playable_game(
    brief: str | Mapping[str, Any],
    *,
    era: str | None = None,
    archetype: Any = _UNSET,
    repair_mode: str = "apply",
    playtest_mode: str = "auto",
    max_rounds: int = 3,
    out: str | None = None,
    overwrite: bool = False,
    binary: str | None = None,
    actor_id: str | None = None,
    tenant_id: str | None = None,
    execution_id: str | None = None,
    project_id: str | None = None,
    planner: PlannerHook | None = None,
    qa: QaHook | None = None,
    deadline_s: float | None = DEFAULT_DEADLINE_S,
    runner: Any = None,
    target: str = "godot",
    answers: Mapping[str, Any] | None = None,
    on_progress: Callable[[float, str], None] | None = None,
) -> dict[str, Any]:
    """Compile a brief, generate content, materialise Godot, and prove the loop.

    This is the only playable-game executor. ``skeleton game``,
    ``POST /api/v1/game/build``, ``skeleton dev game build``, and
    ``POST /api/v1/gameforge/run`` are adapters. Materialisation stays inside
    ``GameForgeRun.execute`` (``Forge.materialise`` / ``godot_emit``).

    ``archetype`` defaults to ``\"auto\"``. Pass ``None`` when a cockpit
    ``BIND ARCHETYPE`` pin must apply. ``deadline_s`` defaults to 120 seconds
    and is one budget for materialisation, content, every prove round, the
    QA repair pass, project write, and both hooks. A stage or hook is not
    entered once the deadline has passed. ``None`` disables it. The returned
    mapping is ``skeleton.game_builder_run.v1``. ``_operator`` is the
    ten-stage report for the legacy HTTP adapter and is stripped by
    ``public_payload``.

    ``planner`` and ``qa`` are optional callables and default to no-ops.
    A planner proposal that changes genre, engine, brief, or scope is
    discarded. ``qa`` returning ``repair_requested`` true runs one more
    ``prove_and_repair`` pass when time remains. A second request is ignored.
    """
    import tempfile
    from pathlib import Path

    from skeleton.context.pipeline import GameForgeRun
    from skeleton.forge.repair import REPAIR_MODES

    structured, text = coerce_brief(brief)
    actor = _optional_id(actor_id, "actor_id")
    tenant = _optional_id(tenant_id, "tenant_id")
    execution = _optional_id(execution_id, "execution_id")
    project = _optional_id(project_id, "project_id")
    identity = {
        "actor_id": actor,
        "tenant_id": tenant,
        "execution_id": execution,
        "project_id": project,
        "structured_brief": structured,
        "deadline_s": deadline_s if deadline_s is not None else None,
    }
    if deadline_s is not None and (isinstance(deadline_s, bool) or not isinstance(deadline_s, (int, float)) or float(deadline_s) < 0):
        raise ValueError("deadline_s must be a non-negative number of seconds or None")
    if not text.strip() and not answers:
        raise ValueError("brief is required")
    mode = normalise_mode(playtest_mode)
    if repair_mode not in REPAIR_MODES:
        raise ValueError(f"repair_mode must be one of {', '.join(REPAIR_MODES)}")
    chosen_archetype = "auto" if archetype is _UNSET else archetype
    started = time.monotonic()
    deadline_at = None if deadline_s is None else started + float(deadline_s)

    def halt(**kwargs: Any) -> dict[str, Any]:
        return _deadline_halt(on_progress, identity, qa=qa, **kwargs)

    if _expired(deadline_at):
        return halt()
    _progress(on_progress, 0.05, "compiling brief")
    _progress(on_progress, 0.2, "materialising")
    engine = runner if runner is not None else GameForgeRun()

    def _execute() -> Any:
        return engine.execute(
            text.strip(),
            era=era or None,
            archetype=chosen_archetype,
            target=target,
            answers=dict(answers) if answers else None,
            playtest="off",
            repair_mode=repair_mode,
        )

    try:
        pipeline = _call_bounded(deadline_at, _execute)
    except TimeoutError:
        return halt()
    if _expired(deadline_at):
        return halt(pipeline=pipeline if isinstance(pipeline, Mapping) else None)
    if not isinstance(pipeline, Mapping):
        raise ValueError("gameforge pipeline returned no report")
    if not pipeline.get("succeeded"):
        if _expired(deadline_at):
            return halt(pipeline=pipeline)
        error = "; ".join(_failed_stages(pipeline)) or "gameforge pipeline failed"
        _progress(on_progress, 0.3, "planning")
        try:
            failed_spec = _apply_planner(
                compile_brief(_resolved_brief_text(text, pipeline), era=str(pipeline.get("era") or "")),
                planner,
                deadline_at=deadline_at,
            )
        except TimeoutError:
            return halt(pipeline=pipeline)
        if _expired(deadline_at):
            return halt(pipeline=pipeline, spec=failed_spec)
        failure = {
            "ok": False,
            "spec": failed_spec,
            "content": None,
            "marker": "",
            "proof": "",
            "check": {"ok": False, "problems": [error]},
            "core_loop": {"passed": False, "marker": ""},
            "playtest": None,
            "repair": {"rounds": 0, "actions": []},
            "files": {},
        }
        qa_report, _requested = _call_qa(qa, _qa_view(failure, failed_spec, None), deadline_at=deadline_at)
        if _expired(deadline_at):
            return halt(pipeline=pipeline, spec=failed_spec, qa_report=qa_report)
        return _attach_qa(
            _blank_result(
                error=error,
                spec=failed_spec,
                check=failure["check"],
                core_loop=failure["core_loop"],
                repair=failure["repair"],
                pipeline={
                    "succeeded": False,
                    "era": pipeline.get("era"),
                    "sim": pipeline.get("sim"),
                },
                _operator=dict(pipeline),
                **identity,
            ),
            qa,
            qa_report,
        )
    if _expired(deadline_at):
        return halt(pipeline=pipeline)
    resolved = _resolved_brief_text(text, pipeline)
    _progress(on_progress, 0.3, "planning")
    try:
        spec = _apply_planner(
            compile_brief(resolved, era=str(pipeline.get("era") or "")),
            planner,
            deadline_at=deadline_at,
        )
    except TimeoutError:
        return halt(pipeline=pipeline)
    if _expired(deadline_at):
        return halt(pipeline=pipeline, spec=spec)
    emitted = pipeline.get("files") if isinstance(pipeline.get("files"), Mapping) else {}
    if target != "godot":
        names = sorted(str(name) for name in emitted)
        rendered = {str(key): str(value) for key, value in emitted.items()}
        view = {
            "ok": True,
            "files": rendered,
            "marker": "",
            "proof": "",
            "check": None,
            "core_loop": None,
            "playtest": None,
            "repair": None,
        }
        if _expired(deadline_at):
            return halt(pipeline=pipeline, spec=spec, files=rendered)
        qa_report, _requested = _call_qa(qa, _qa_view(view, spec, None), deadline_at=deadline_at)
        if _expired(deadline_at):
            return halt(pipeline=pipeline, spec=spec, files=rendered, qa_report=qa_report)
        return _attach_qa(
            _blank_result(
                ok=True,
                spec=spec,
                pipeline={
                    "succeeded": True,
                    "era": pipeline.get("era"),
                    "sim_passed": bool((pipeline.get("sim") or {}).get("passed")),
                    "file_count": (pipeline.get("forge") or {}).get("file_count"),
                    "blueprint_id": (pipeline.get("forge") or {}).get("blueprint_id"),
                },
                file_names=names,
                files=rendered,
                _operator=dict(pipeline),
                **identity,
            ),
            qa,
            qa_report,
        )
    _progress(on_progress, 0.4, "generating content")
    with tempfile.TemporaryDirectory(prefix="game-builder-quality-") as quality_root:
        from skeleton.forge.eras import compile_era

        if _expired(deadline_at):
            return halt(pipeline=pipeline, spec=spec)

        def _content() -> Any:
            return generate_content(spec, emitted, root=Path(quality_root))

        try:
            content = _call_bounded(deadline_at, _content)
        except TimeoutError:
            return halt(pipeline=pipeline, spec=spec)
        if _expired(deadline_at):
            return halt(pipeline=pipeline, spec=spec, content=content)
        files = attach_genre(emitted, spec, content)
        if _expired(deadline_at):
            return halt(pipeline=pipeline, spec=spec, content=content, files=files)
        pack = compile_era(str(pipeline.get("era") or "extraction_now"))
        remaining = _remaining(deadline_at)
        if remaining is not None and remaining <= 0:
            return halt(pipeline=pipeline, spec=spec, content=content, files=files)
        _progress(on_progress, 0.55, "proving")
        proved = prove_and_repair(
            files,
            spec,
            content,
            playtest_mode=mode,
            max_rounds=max_rounds,
            pack=pack,
            binary=binary,
            root=Path(quality_root),
            deadline_s=None if deadline_at is None else max(0.0, remaining),
            on_progress=on_progress,
        )
        if _proof_stopped(proved, deadline_at):
            return halt(pipeline=pipeline, spec=spec, content=content, proved=proved)
        _progress(on_progress, 0.7, "qa")
        qa_report, repair_requested = _call_qa(
            qa, _qa_view(proved, spec, content), deadline_at=deadline_at,
        )
        if _expired(deadline_at):
            return halt(pipeline=pipeline, spec=spec, content=content, proved=proved, qa_report=qa_report)
        if repair_requested:
            remaining = _remaining(deadline_at)
            if remaining is not None and remaining <= 0:
                return halt(pipeline=pipeline, spec=spec, content=content, proved=proved, qa_report=qa_report)
            _progress(on_progress, 0.75, "qa repair")
            proved = prove_and_repair(
                proved["files"],
                spec,
                content,
                playtest_mode=mode,
                max_rounds=max_rounds,
                pack=pack,
                binary=binary,
                root=Path(quality_root),
                deadline_s=None if deadline_at is None else max(0.0, remaining),
                on_progress=on_progress,
            )
            if _proof_stopped(proved, deadline_at):
                return halt(pipeline=pipeline, spec=spec, content=content, proved=proved, qa_report=qa_report)
            qa_report, _again = _call_qa(qa, _qa_view(proved, spec, content), deadline_at=deadline_at)
            if _expired(deadline_at):
                return halt(pipeline=pipeline, spec=spec, content=content, proved=proved, qa_report=qa_report)
        proved_files = dict(proved.pop("files"))
    ok = bool(proved["ok"])
    written = None
    if out and ok:
        from skeleton.forge.projector import write_project

        if _expired(deadline_at):
            return halt(pipeline=pipeline, spec=spec, content=content, proved=proved, files=proved_files, qa_report=qa_report)
        _progress(on_progress, 0.92, "writing project")

        def _write() -> Any:
            return write_project(
                out,
                proved_files,
                overwrite=overwrite,
                meta={"spec_id": spec["spec_id"], "genre": spec["genre"], "schema": SCHEMA_VERSION},
            )

        try:
            written = _call_bounded(deadline_at, _write)
        except TimeoutError:
            return halt(pipeline=pipeline, spec=spec, content=content, proved=proved, files=proved_files, qa_report=qa_report)
    if _expired(deadline_at):
        return halt(pipeline=pipeline, spec=spec, content=content, proved=proved, files=proved_files, qa_report=qa_report)
    _progress(on_progress, 1.0, "complete" if ok else "failed")
    body = _blank_result(
        ok=ok,
        spec=spec,
        content=content,
        marker=proved["marker"],
        proof=proved["proof"],
        check=proved["check"],
        core_loop=proved["core_loop"],
        playtest=proved["playtest"],
        repair=proved["repair"],
        pipeline={
            "succeeded": True,
            "era": pipeline.get("era"),
            "sim_passed": bool((pipeline.get("sim") or {}).get("passed")),
            "file_count": (pipeline.get("forge") or {}).get("file_count"),
            "blueprint_id": (pipeline.get("forge") or {}).get("blueprint_id"),
        },
        project=written,
        file_names=sorted(proved_files),
        files=proved_files,
        _operator=dict(pipeline),
        **identity,
    )
    if not proved["ok"]:
        body["error"] = "; ".join((proved.get("check") or {}).get("problems") or []) or "proof failed"
    return _attach_qa(body, qa, qa_report)


def public_payload(result: Mapping[str, Any], *, include_files: bool = False) -> dict[str, Any]:
    """Return the frozen ``skeleton.game_builder_run.v1`` body.

    Inline ``files`` are omitted above 8 MiB. The operator pipeline report
    is not part of the contract.
    """
    body = {key: result[key] for key in RESULT_FIELDS if key in result}
    if result.get("error"):
        body["error"] = result["error"]
    files = result.get("files")
    body["file_names"] = sorted(files) if isinstance(files, Mapping) else list(result.get("file_names") or [])
    if include_files and isinstance(files, Mapping):
        encoded = sum(len(str(value).encode("utf-8")) for value in files.values())
        if encoded > MAX_INLINE_FILE_BYTES:
            body["files_omitted"] = True
            body["files_bytes"] = encoded
        else:
            body["files"] = {str(key): str(value) for key, value in files.items()}
    return body


def project_operator_http(result: Mapping[str, Any], *, include_files: bool = False) -> dict[str, Any]:
    """Project a builder result back onto the ten-stage ``/gameforge/run`` body."""
    from skeleton.forge.source_manifest import source_manifest

    operator = result.get("_operator")
    body = dict(operator) if isinstance(operator, Mapping) else {"succeeded": bool(result.get("ok"))}
    files = result.get("files")
    if not isinstance(files, Mapping) or not files:
        files = body.get("files") if isinstance(body.get("files"), Mapping) else {}
    rendered = {str(key): str(value) for key, value in files.items()}
    body["file_names"] = sorted(rendered)
    if rendered:
        try:
            body["source_manifest"] = source_manifest(rendered)
        except (TypeError, ValueError):
            pass
    if "ok" in result:
        body["succeeded"] = bool(result.get("ok")) and bool(body.get("succeeded", True))
    if result.get("playtest") is not None:
        body["playtest"] = result["playtest"]
    if include_files:
        encoded = sum(len(value.encode("utf-8")) for value in rendered.values())
        if encoded > MAX_INLINE_FILE_BYTES:
            body.pop("files", None)
            body["files_omitted"] = True
            body["files_bytes"] = encoded
        else:
            body["files"] = rendered
    else:
        body.pop("files", None)
    return body


def cli(argv: Sequence[str]) -> int:
    """``python -m skeleton game`` implementation."""
    out: Optional[str] = None
    overwrite = False
    as_json = False
    playtest_mode = "auto"
    max_rounds = 3
    words: list[str] = []
    rest = list(argv)
    index = 0
    try:
        while index < len(rest):
            token = rest[index]
            if token == "--out":
                if index + 1 >= len(rest):
                    raise ValueError("--out needs a directory")
                out = rest[index + 1]
                index += 2
            elif token == "--playtest":
                if index + 1 >= len(rest):
                    raise ValueError("--playtest needs off, auto, or require")
                playtest_mode = normalise_mode(rest[index + 1])
                index += 2
            elif token == "--max-rounds":
                if index + 1 >= len(rest):
                    raise ValueError("--max-rounds needs an integer")
                max_rounds = int(rest[index + 1])
                if not 1 <= max_rounds <= 3:
                    raise ValueError("--max-rounds must be from 1 to 3")
                index += 2
            elif token == "--overwrite":
                overwrite = True
                index += 1
            elif token == "--json":
                as_json = True
                index += 1
            elif token.startswith("-"):
                raise ValueError(f"unknown game option: {token}")
            else:
                words.append(token)
                index += 1
        brief = " ".join(words).strip()
        if not brief:
            raise ValueError("a game brief is required")
        result = build_playable_game(
            brief,
            playtest_mode=playtest_mode,
            max_rounds=max_rounds,
            out=out,
            overwrite=overwrite,
        )
    except (ValueError, OSError) as exc:
        print(f"game: {exc}", file=sys.stderr)
        return 2
    shown = public_payload(result, include_files=False)
    if as_json:
        print(json.dumps(shown, indent=2, sort_keys=True, default=str))
    else:
        spec = shown.get("spec") or {}
        print(
            f"ok={shown.get('ok')} genre={spec.get('genre')} "
            f"era={spec.get('era')} marker={shown.get('marker')} "
            f"files={len(shown.get('file_names') or [])}"
        )
        project = shown.get("project") or {}
        if isinstance(project, Mapping) and project.get("root"):
            print("wrote", project["root"])
        if not shown.get("ok"):
            print(shown.get("error") or shown.get("check") or shown.get("playtest"))
    return 0 if result.get("ok") else 1
