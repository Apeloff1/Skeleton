"""Brief → playable Godot project.

One entry point over the existing GameForge run, era/room materialiser,
static GDScript checker, forge repair pass, and headless Godot playtest.
The design spec and content bundle are committed by this module; Godot is
the engine target. Repair reads checker and engine errors and retries a
bounded number of times.

``planner`` and ``qa`` are optional hooks. The default is a no-op. A planner
may enrich ``skeleton.game_design_spec.v1`` without changing the committed
genre, engine, brief, or scope. QA reviews the checker, core loop, and
Godot playtest. When QA sets ``repair_requested``, this function runs one
more ``prove_and_repair`` pass. Hooks do not materialise a second project.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

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
STUBBED = (
    "authored sprites, meshes, and audio",
    "input-driven play beyond the headless core-loop proof",
    "multiplayer, persistence past the economy ledger, and store packaging",
    "provider model proposals; the deterministic compiler is the commit authority",
    "vehicle dynamics past one kinematic integration proof",
)

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


def _apply_planner(spec: Mapping[str, Any], planner: PlannerHook | None) -> dict[str, Any]:
    """Keep the compiled spec when a hook is missing or proposes a different game."""
    committed = dict(spec)
    if planner is None:
        return committed
    try:
        proposed = planner(dict(committed))
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


def _call_qa(qa: QaHook | None, view: Mapping[str, Any]) -> tuple[dict[str, Any] | None, bool]:
    if qa is None:
        return None, False
    try:
        review = qa(dict(view))
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
) -> dict[str, Any]:
    """Check, execute the core loop, boot Godot when requested, and repair."""
    from skeleton.forge.gdscript_check import check_files

    mode = normalise_mode(playtest_mode)
    if isinstance(max_rounds, bool) or not isinstance(max_rounds, int) or not 1 <= max_rounds <= 3:
        raise ValueError("max_rounds must be an integer from 1 to 3")
    current = dict(files)
    actions: list[dict[str, Any]] = []
    problems: list[str] = []
    report: dict[str, Any] | None = None
    marker = ""
    rounds = 0
    ok = False
    genre = str(spec.get("genre") or "")
    while rounds < max_rounds:
        rounds += 1
        problems = check_files(current)
        marker = execute_core_loop(content, genre)
        errors = list(problems)
        if not loop_succeeded(marker):
            errors.append(f"core loop marker {marker!r}")
        report = None
        if not errors and mode != "off":
            report = playtest(current, binary=binary, frames=20, timeout=90)
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


def build_playable_game(
    brief: str,
    *,
    era: str | None = None,
    archetype: str | None = None,
    repair_mode: str = "apply",
    playtest_mode: str = "auto",
    max_rounds: int = 3,
    out: str | None = None,
    overwrite: bool = False,
    binary: str | None = None,
    planner: PlannerHook | None = None,
    qa: QaHook | None = None,
) -> dict[str, Any]:
    """Compile a brief, generate content, materialise Godot, and prove the loop.

    This is the single playable-game executor. The CLI, ``POST /api/v1/game/build``,
    ``skeleton dev game build``, and the unmounted ``gameforge_routes`` run
    handler all call it. The ten-stage operator pipeline stays inside.
    ``planner`` and ``qa`` default to no-ops so existing callers stay unchanged.
    """
    import tempfile
    from pathlib import Path

    from skeleton.context.pipeline import GameForgeRun
    from skeleton.forge.repair import REPAIR_MODES

    mode = normalise_mode(playtest_mode)
    if repair_mode not in REPAIR_MODES:
        raise ValueError(f"repair_mode must be one of {', '.join(REPAIR_MODES)}")
    spec = compile_brief(brief)
    pipeline = GameForgeRun().execute(
        spec["brief"],
        era=era or None,
        archetype=archetype or "auto",
        target="godot",
        playtest="off",
        repair_mode=repair_mode,
    )
    if not pipeline.get("succeeded"):
        error = "; ".join(_failed_stages(pipeline)) or "gameforge pipeline failed"
        spec = _apply_planner(compile_brief(brief, era=str(pipeline.get("era") or "")), planner)
        failure = {
            "ok": False,
            "spec": spec,
            "content": None,
            "marker": "",
            "proof": "",
            "check": {"ok": False, "problems": [error]},
            "core_loop": {"passed": False, "marker": ""},
            "playtest": None,
            "repair": {"rounds": 0, "actions": []},
            "files": {},
        }
        qa_report, _requested = _call_qa(qa, _qa_view(failure, spec, None))
        return _attach_qa(
            {
                "schema_version": RUN_SCHEMA,
                "ok": False,
                "error": error,
                "spec": spec,
                "content": None,
                "pipeline": {
                    "succeeded": False,
                    "era": pipeline.get("era"),
                    "sim": pipeline.get("sim"),
                },
                "stubbed": list(STUBBED),
            },
            qa,
            qa_report,
        )
    spec = _apply_planner(compile_brief(brief, era=str(pipeline.get("era") or "")), planner)
    qa_report: dict[str, Any] | None = None
    with tempfile.TemporaryDirectory(prefix="game-builder-quality-") as quality_root:
        from skeleton.forge.eras import compile_era

        content = generate_content(spec, pipeline.get("files") or {}, root=Path(quality_root))
        files = attach_genre(pipeline.get("files") or {}, spec, content)
        pack = compile_era(str(pipeline.get("era") or "extraction_now"))
        proved = prove_and_repair(
            files,
            spec,
            content,
            playtest_mode=mode,
            max_rounds=max_rounds,
            pack=pack,
            binary=binary,
            root=Path(quality_root),
        )
        qa_report, repair_requested = _call_qa(qa, _qa_view(proved, spec, content))
        if repair_requested:
            proved = prove_and_repair(
                proved["files"],
                spec,
                content,
                playtest_mode=mode,
                max_rounds=max_rounds,
                pack=pack,
                binary=binary,
                root=Path(quality_root),
            )
            qa_report, _again = _call_qa(qa, _qa_view(proved, spec, content))
    project = None
    if out and proved["ok"]:
        from skeleton.forge.projector import write_project

        project = write_project(
            out,
            proved["files"],
            overwrite=overwrite,
            meta={"spec_id": spec["spec_id"], "genre": spec["genre"], "schema": SCHEMA_VERSION},
        )
    proved_files = proved.pop("files")
    body = {
        "schema_version": RUN_SCHEMA,
        "ok": bool(proved["ok"]),
        "spec": spec,
        "content_schema": CONTENT_SCHEMA,
        "content": content,
        "marker": proved["marker"],
        "proof": proved["proof"],
        "check": proved["check"],
        "core_loop": proved["core_loop"],
        "playtest": proved["playtest"],
        "repair": proved["repair"],
        "pipeline": {
            "succeeded": True,
            "era": pipeline.get("era"),
            "sim_passed": bool((pipeline.get("sim") or {}).get("passed")),
            "file_count": (pipeline.get("forge") or {}).get("file_count"),
            "blueprint_id": (pipeline.get("forge") or {}).get("blueprint_id"),
        },
        "project": project,
        "file_names": sorted(proved_files),
        "files": proved_files,
        "stubbed": list(STUBBED),
    }
    return _attach_qa(body, qa, qa_report)


def public_payload(result: Mapping[str, Any], *, include_files: bool = False) -> dict[str, Any]:
    body = dict(result)
    files = body.pop("files", None)
    body["file_names"] = sorted(files) if isinstance(files, Mapping) else list(body.get("file_names") or [])
    if include_files and isinstance(files, Mapping):
        body["files"] = dict(files)
    return body


def cli(argv: Sequence[str]) -> int:
    """``python -m skeleton game`` implementation."""
    out: str | None = None
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
