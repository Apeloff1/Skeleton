"""Deterministic role handlers.

Each handler reads upstream artefacts, recalls project memory, and writes its
handoff. Model text is not required. A caller can still inject a model at
plan time; these handlers stay replayable.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Mapping

from skeleton.automation.swarm.studio.loop import SCHEMA, assemble_playable, template_for
from skeleton.automation.swarm.studio.memory import ProjectMemory
from skeleton.automation.swarm.studio.playtester import playtest_project
from skeleton.automation.swarm.studio.tools import StudioTools


ForgeRunner = Callable[[dict[str, Any]], dict[str, Any]]


class ExecContext:
    def __init__(
        self,
        *,
        brief: Mapping[str, Any],
        artefacts: Mapping[str, Mapping[str, Any]],
        memory: ProjectMemory,
        tools: StudioTools,
        forge_runner: ForgeRunner | None,
    ) -> None:
        self.brief = brief
        self.artefacts = artefacts
        self.memory = memory
        self.tools = tools
        self.forge_runner = forge_runner


def run_director(ctx: ExecContext) -> dict[str, Any]:
    recalled = ctx.memory.recall(str(ctx.brief.get("title") or "game"), top_k=ctx.memory.top_k)
    pillar = "Ship a bootable loop before adding scope."
    if recalled:
        pillar = f"{pillar} Prior notes: {len(recalled)}."
    artefact = {
        "title": ctx.brief["title"],
        "pillar": pillar,
        "milestones": ["design", "build", "playtest"],
        "constraints": list(ctx.brief.get("constraints") or []),
    }
    _write_json(ctx.tools, "director.json", artefact)
    ctx.memory.remember("decision", f"pillar for {ctx.brief['title']}: {pillar}", tags=["decision", "director"])
    for constraint in artefact["constraints"]:
        ctx.memory.remember("constraint", f"honor constraint {constraint}", tags=["constraint"])
    return artefact


def run_design(ctx: ExecContext) -> dict[str, Any]:
    sheet = template_for(str(ctx.brief["genre"]), list(ctx.brief.get("constraints") or []))
    artefact = {
        "core_loop": list(sheet["core_loop"]),
        "verbs": list(sheet["verbs"]),
        "win": sheet["win"],
        "fantasy": f"A small playable {ctx.brief['genre']} loop.",
    }
    _write_json(ctx.tools, "design.json", artefact)
    ctx.memory.remember(
        "decision",
        "core loop " + " ".join(artefact["core_loop"]),
        tags=["decision", "design"],
    )
    return artefact


def run_systems(ctx: ExecContext) -> dict[str, Any]:
    design = ctx.artefacts["design"]
    artefact = {
        "mechanics": "The player moves, resolves the local action, then collects the reward.",
        "verbs": list(design.get("verbs") or []),
    }
    _write_json(ctx.tools, "systems.json", artefact)
    return artefact


def run_level(ctx: ExecContext) -> dict[str, Any]:
    sheet = template_for(str(ctx.brief["genre"]), list(ctx.brief.get("constraints") or []))
    artefact = {"rooms": sheet["rooms"], "start_room": sheet["start_room"]}
    _write_json(ctx.tools, "level.json", artefact)
    return artefact


def run_narrative(ctx: ExecContext) -> dict[str, Any]:
    speaker = "guide"
    if "small-cast" in (ctx.brief.get("constraints") or []):
        speaker = "narrator"
    artefact = {"beats": ["arrive", "act", "leave"], "speaker": speaker}
    _write_json(ctx.tools, "narrative.json", artefact)
    return artefact


def run_art(ctx: ExecContext) -> dict[str, Any]:
    ctx.tools.generate_asset("sprite", "hero silhouette")
    ctx.tools.generate_asset("backdrop", "yard gate")
    artefact = {"assets": ["sprite-hero", "backdrop-yard"]}
    _write_json(ctx.tools, "art_manifest.json", artefact)
    return artefact


def run_audio(ctx: ExecContext) -> dict[str, Any]:
    artefact = {"cues": ["start", "act", "win"]}
    _write_json(ctx.tools, "audio_cues.json", artefact)
    return artefact


def run_integrate(ctx: ExecContext) -> dict[str, Any]:
    playable = assemble_playable(
        ctx.brief,
        design=ctx.artefacts["design"],
        level=ctx.artefacts["level"],
        narrative=ctx.artefacts["narrative"],
        art=ctx.artefacts["art"],
        audio=ctx.artefacts["audio"],
    )
    if playable.get("schema") != SCHEMA:
        raise RuntimeError("playable schema drifted")
    _write_json(ctx.tools, "playable.json", playable)
    if ctx.forge_runner is not None:
        answers = {"title": ctx.brief["title"], "genre": ctx.brief["genre"], "theme": "playable"}
        pitch = ctx.brief.get("pitch")
        if isinstance(pitch, str) and pitch.strip():
            answers["pitch"] = pitch
        try:
            spec = ctx.forge_runner(dict(answers))
        except Exception:
            ctx.memory.remember("failure", "forge runner failed", tags=["failure", "forge"])
        else:
            if isinstance(spec, dict) and spec:
                _write_json(ctx.tools, "gameforge_spec.json", spec)
    return playable


def run_repair(ctx: ExecContext) -> dict[str, Any]:
    """Rebuild the playable without constraints QA already proved are blocking."""
    brief = dict(ctx.brief)
    brief["constraints"] = [
        item for item in brief.get("constraints") or [] if item != "omit-win-item"
    ]
    sheet = template_for(str(brief["genre"]), list(brief["constraints"]))
    design = dict(ctx.artefacts.get("design") or {})
    design["win"] = sheet["win"]
    design.setdefault("core_loop", sheet["core_loop"])
    design.setdefault("verbs", sheet["verbs"])
    level = {"rooms": sheet["rooms"], "start_room": sheet["start_room"]}
    playable = assemble_playable(
        brief,
        design=design,
        level=level,
        narrative=ctx.artefacts.get("narrative") or {"beats": ["arrive"], "speaker": "guide"},
        art=ctx.artefacts.get("art") or {"assets": ["sprite-hero"]},
        audio=ctx.artefacts.get("audio") or {"cues": ["start"]},
    )
    _write_json(ctx.tools, "level.json", level)
    _write_json(ctx.tools, "playable.json", playable)
    ctx.memory.remember("decision", "repair placed the missing win item", tags=["decision", "repair"])
    return {"summary": "rebuilt playable without the blocking constraint", "playable": "rewritten"}


def run_qa(ctx: ExecContext) -> dict[str, Any]:
    report = playtest_project(ctx.tools, ctx.brief)
    for issue in report["issues"]:
        if issue.get("severity") == "blocker":
            ctx.memory.remember("failure", str(issue["summary"]), tags=["failure", "qa"])
    artefact = {
        "summary": _summary(report),
        "booted": report["booted"],
        "loop_works": report["loop_works"],
        "won": report["won"],
        "spec_coverage": report["spec_coverage"],
        "issues": report["issues"],
        "ticks": report["ticks"],
        "verbs": report["verbs"],
    }
    _write_json(ctx.tools, "qa_report.json", {key: artefact[key] for key in ("summary", "booted", "loop_works", "won")})
    return artefact


def _summary(report: Mapping[str, Any]) -> str:
    if report.get("won"):
        return "core loop reached the win condition"
    issues = report.get("issues") or []
    if issues:
        return str(issues[0].get("summary") or "playtest found a defect")
    return "playtest finished without a win"


def _write_json(tools: StudioTools, relative: str, payload: Mapping[str, Any]) -> None:
    tools.write_text(relative, json.dumps(payload, sort_keys=True, indent=2) + "\n")


HANDLERS = {
    "studio.director": run_director,
    "studio.design": run_design,
    "studio.systems": run_systems,
    "studio.level": run_level,
    "studio.narrative": run_narrative,
    "studio.art": run_art,
    "studio.audio": run_audio,
    "studio.integrate": run_integrate,
    "studio.repair": run_repair,
    "studio.qa": run_qa,
}
