"""Planning-role handlers.

Each handler leaves a handoff artefact and a note under ``studio/``. None of
them writes a playable project. Godot output belongs to ``build_playable_game``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from skeleton.automation.swarm.studio.memory import ProjectMemory
from skeleton.automation.swarm.studio.tools import StudioTools

_VERBS = {
    "top_down_shooter": ("move", "aim", "clear"),
    "platformer": ("run", "jump"),
    "rpg_roguelike": ("enter", "fight", "pay"),
}


@dataclass
class ExecContext:
    spec: dict[str, Any]
    memory: ProjectMemory
    tools: StudioTools


def run_director(ctx: ExecContext) -> dict[str, Any]:
    title = str(ctx.spec.get("title") or "Game")
    pillar = str(ctx.spec.get("fantasy") or title)
    artefact = {
        "id": "studio-director",
        "title": title[:48],
        "pillar": pillar[:180],
        "milestones": ["plan", "build", "qa"],
    }
    ctx.memory.remember("decision", f"pillar: {artefact['pillar']}", tags=["decision", "director"])
    _write(ctx, "studio/director.json", artefact)
    return artefact


def run_design(ctx: ExecContext) -> dict[str, Any]:
    genre = str(ctx.spec.get("genre") or "")
    artefact = {
        "id": "studio-design",
        "core_loop": str(ctx.spec.get("core_loop") or "")[:180],
        "fantasy": str(ctx.spec.get("fantasy") or "")[:180],
        "verbs": list(_VERBS.get(genre, ("play",))),
        "win": str(ctx.spec.get("core_loop") or "finish the loop")[:180],
    }
    ctx.memory.remember("decision", f"core loop: {artefact['core_loop']}", tags=["decision", "design"])
    _write(ctx, "studio/design.json", artefact)
    return artefact


def run_systems(ctx: ExecContext) -> dict[str, Any]:
    systems = [str(item) for item in (ctx.spec.get("systems") or [])][:8]
    artefact = {
        "id": "studio-systems",
        "mechanics": systems or ["levels"],
        "verbs": list(_VERBS.get(str(ctx.spec.get("genre") or ""), ("play",))),
    }
    ctx.memory.remember("constraint", "mechanics follow the compiled systems list", tags=["constraint", "systems"])
    _write(ctx, "studio/systems.json", artefact)
    return artefact


def run_level(ctx: ExecContext) -> dict[str, Any]:
    artefact = {
        "id": "studio-level",
        "rooms": [str(ctx.spec.get("genre") or "space")],
        "start_room": "start",
        "layout": f"one {ctx.spec.get('scope') or 'small'} {ctx.spec.get('genre') or 'space'}",
    }
    _write(ctx, "studio/level.json", artefact)
    return artefact


def run_narrative(ctx: ExecContext) -> dict[str, Any]:
    fantasy = str(ctx.spec.get("fantasy") or "the job")
    artefact = {
        "id": "studio-narrative",
        "beats": [fantasy[:80], "the loop pays off"],
        "speaker": "narrator",
    }
    _write(ctx, "studio/narrative.json", artefact)
    return artefact


def run_art(ctx: ExecContext) -> dict[str, Any]:
    artefact = {"id": "studio-art", "assets": ["placeholder"]}
    ctx.tools.generate_asset("sprite", str(ctx.spec.get("title") or "placeholder"))
    _write(ctx, "studio/art.json", artefact)
    return artefact


def run_audio(ctx: ExecContext) -> dict[str, Any]:
    artefact = {"id": "studio-audio", "cues": ["loop-start", "loop-end"]}
    _write(ctx, "studio/audio.json", artefact)
    return artefact


def run_qa(ctx: ExecContext, review: dict[str, Any]) -> dict[str, Any]:
    passed = bool(review.get("passed"))
    artefact = {
        "id": "studio-qa",
        "summary": "godot review" if passed else "godot review filed blockers",
        "passed": passed,
    }
    if not passed:
        ctx.memory.remember("failure", artefact["summary"], tags=["failure", "qa"])
    _write(ctx, "studio/qa.json", artefact)
    return artefact


HANDLERS: dict[str, Callable[[ExecContext], dict[str, Any]]] = {
    "studio.director": run_director,
    "studio.design": run_design,
    "studio.systems": run_systems,
    "studio.level": run_level,
    "studio.narrative": run_narrative,
    "studio.art": run_art,
    "studio.audio": run_audio,
}


def _write(ctx: ExecContext, relative: str, artefact: dict[str, Any]) -> None:
    ctx.tools.write_text(relative, json.dumps(artefact, sort_keys=True))
