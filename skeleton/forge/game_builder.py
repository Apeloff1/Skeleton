"""Brief → playable Godot project.

One entry point over the existing GameForge run, era/room materialiser,
static GDScript checker, forge repair pass, and headless Godot playtest.
The design spec and content bundle are committed by this module; Godot is
the engine target. Repair reads checker and engine errors and retries a
bounded number of times.
"""
from __future__ import annotations

import json
import sys
from typing import Any, Mapping, Optional, Sequence

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
) -> dict[str, Any]:
    """Compile a brief, generate content, materialise Godot, and prove the loop.

    This is the single playable-game executor. The CLI, ``POST /api/v1/game/build``,
    ``skeleton dev game build``, and the unmounted ``gameforge_routes`` run
    handler all call it. The ten-stage operator pipeline stays inside.
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
        return {
            "schema_version": RUN_SCHEMA,
            "ok": False,
            "error": "; ".join(_failed_stages(pipeline)) or "gameforge pipeline failed",
            "spec": compile_brief(brief, era=str(pipeline.get("era") or "")),
            "content": None,
            "pipeline": {
                "succeeded": False,
                "era": pipeline.get("era"),
                "sim": pipeline.get("sim"),
            },
            "stubbed": list(STUBBED),
        }
    spec = compile_brief(brief, era=str(pipeline.get("era") or ""))
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
    return {
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


def public_payload(result: Mapping[str, Any], *, include_files: bool = False) -> dict[str, Any]:
    body = dict(result)
    files = body.pop("files", None)
    body["file_names"] = sorted(files) if isinstance(files, Mapping) else list(body.get("file_names") or [])
    if include_files and isinstance(files, Mapping):
        body["files"] = dict(files)
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
