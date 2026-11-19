"""Executable original multi-stage quest and cinematic scene generator.

Designers can change every scene, camera, cast, cutscene timeline, action,
quest solution and narrative premise via a strict blueprint parser. The
generator creates independent playable methods, not rigid quest answers.
"""
from __future__ import annotations

from dataclasses import fields
import json
from pathlib import Path
import random

from .contracts import canonical_digest
from .authored_tiles import _no_duplicate_keys, _json_number_reject
from .quest_scene_engine import (
    ARCHETYPES, Affordance, Cue, Cutscene, DirectorError, DirectorWorld,
    NarrativeBible, Parameter, QuestArc, QuestStage, Scene, Solution,
)

METHODS = {
    "escort_path": ("escort_follow", "protect", "negotiate"),
    "escort_leash": ("escort_leash", "heal", "protect"),
    "escort_introduction": ("escort_introduce", "talk", "trade"),
    "combat": ("fight", "pacify", "sneak"),
    "timed_combat": ("fight", "reinforce", "protect"),
    "rival_combat": ("fight", "negotiate", "protect"),
    "timed_rival_combat": ("fight", "pacify", "sneak"),
    "survival_waves": ("survive", "protect", "reinforce"),
    "dungeoneering": ("fight", "solve", "sneak"),
    "acquisition": ("gather", "trade", "discover"),
    "courier": ("deliver", "trade", "travel"),
    "proficiency": ("train", "solve", "research"),
    "attunement": ("attune", "research", "solve"),
    "profession": ("craft", "repair", "trade"),
    "infusion": ("infuse", "research", "craft"),
    "puzzle": ("solve", "research", "inspect"),
    "stealth": ("sneak", "negotiate", "discover"),
    "rival": ("fight", "negotiate", "sneak"),
    "rival_story": ("negotiate", "discover", "fight"),
    "reinforcement": ("reinforce", "build", "protect"),
    "gathering": ("gather", "research", "trade"),
    "negotiation": ("negotiate", "trade", "talk"),
    "crafting": ("craft", "trade", "research"),
    "repair": ("repair", "craft", "build"),
    "rescue": ("heal", "protect", "sneak"),
    "investigation": ("inspect", "research", "talk"),
    "repeatable": ("gather", "trade", "repair"),
    "regional_story": ("protect", "repair", "negotiate"),
    "main_story": ("research", "negotiate", "discover"),
}
DEFAULT_METHODS = ("interact", "research", "negotiate")
MAX_BYTES = 1_200_000


def forge_director(project_id: str, *, seed: int, regions: tuple[str, ...],
                   quest_types: tuple[str, ...], stages: int = 3,
                   main_goal: str = "Secure the future of the shared world.",
                   placement: str = "seeded") -> DirectorWorld:
    if (not isinstance(quest_types, tuple) or not 1 <= len(quest_types) <= 48
            or any(t not in ARCHETYPES for t in quest_types)
            or type(stages) is not int or not 2 <= stages <= 12
            or not isinstance(regions, tuple) or not 4 <= len(regions) <= 24):
        raise DirectorError("bounded typed multi-stage authoring arguments required")
    if quest_types[0] != "main_story":
        raise DirectorError("first quest must maintain the narrative spine")
    if placement not in {"story", "seeded", "regional", "player_choice"}:
        raise DirectorError("unrecognized story placement mode")
    if type(seed) is not int or not 0 <= seed <= 2**63 - 1:
        raise DirectorError("invalid forge seed")
    rng = random.Random(seed)
    affordances = [[] for _ in regions]
    cinematics = [[] for _ in regions]
    quest_items = []
    for index, archetype in enumerate(quest_types):
        stages_out = []
        approaches = METHODS.get(archetype, DEFAULT_METHODS)
        for step in range(stages):
            slot = ((index + step) % len(regions) if placement == "story"
                    else rng.randrange(len(regions)))
            site = f"scene_{slot:02d}"
            objective = f"objective_{index:02d}_{step:02d}"
            routes = []
            for route_index, kind in enumerate(approaches):
                affordances[slot].append(Affordance(
                    key=f"action_{index:02d}_{step:02d}_{route_index}",
                    kind=kind, target=objective, effort=4 - route_index,
                    quality=("ordinary", "creative", "ingenious")[route_index],
                    proximity=3 if kind == "escort_leash" else 0,
                ))
                routes.append(Solution(
                    f"method_{route_index}",
                    (Parameter(kind, objective),),
                    (0, 30, 75)[route_index], f"outcome_{kind}",
                ))
            extra = f"insight_{index:02d}_{step:02d}"
            affordances[slot].append(Affordance(
                f"optional_{index:02d}_{step:02d}", "inspect", extra,
            ))
            cut_key = f"cut_{index:02d}_{step:02d}"
            name = archetype.replace("_", " ").title()
            cinematics[slot].append(Cutscene(
                cut_key, f"{name}: Act {step + 1}", True, (
                    Cue(0, "camera_cut", site, "wide original establishing shot"),
                    Cue(400, "lighting", site, "soft amber sky", 400),
                    Cue(1000, "actor_emote", "hero", "react to outcome", 600),
                    Cue(1600, "subtitle", site,
                        f"{name} deepens the story. {main_goal}", 1900),
                    Cue(3700, "music_cue", site, "original_theme", 500),
                ), trigger="on_stage_complete",
            ))
            stages_out.append(QuestStage(
                f"stage_{step:02d}", f"{name} — Chapter {step + 1}",
                f"A new consequence of the central crisis must be faced. {main_goal}",
                (site,), tuple(routes),
                (Parameter("inspect", extra),), 14,
                None, cut_key,
            ))
        scope = ("main" if index == 0 else
                 "repeatable" if archetype == "repeatable" else
                 "rival" if "rival" in archetype else
                 "region" if archetype.startswith("regional") else "side")
        quest_items.append(QuestArc(
            f"quest_{index:02d}", archetype.replace("_", " ").title(),
            scope, archetype, "original world renewal",
            f"Choose how to tackle {archetype.replace('_',' ')} challenges.",
            f"The world needs care in {regions[index % len(regions)]}.",
            f"The chosen method affects the path to {main_goal}",
            tuple(stages_out),
            ("quest_00",) if index > 0 and archetype in (
                "rival_story", "main_chain", "epilogue"
            ) else (),
            placement, 3 if archetype == "repeatable" else 1,
            ("stewardship", "discovery", "independence")[index % 3],
        ))
    scenes = []
    for index, region in enumerate(regions):
        if not isinstance(region, str) or not region.isidentifier():
            raise DirectorError("scene regions require symbolic identifiers")
        prev = f"scene_{(index - 1) % len(regions):02d}"
        nxt = f"scene_{(index + 1) % len(regions):02d}"
        if len(affordances[index]) > 64 or len(cinematics[index]) > 16:
            raise DirectorError("scene allocation exceeds live action/cutscene budget")
        scenes.append(Scene(
            f"scene_{index:02d}", region,
            f"{region.replace('_', ' ').title()} — Original Scene",
            "An original living set with authored props and environmental storytelling.",
            "isometric wide", "dynamic ambient", "clear", "original score",
            ("hero", "companion", "rival"),
            ("bridge", "lantern", "marker"),
            tuple(affordances[index] or [Affordance(
                f"ambient_{index}", "inspect", f"environment_{index}"
            )]),
            tuple(cinematics[index]), tuple(dict.fromkeys((prev, nxt))),
        ))
    return DirectorWorld(
        project_id, seed, NarrativeBible(
            "Shared hope amid a changing world.",
            "The community meets the crisis together.",
            main_goal,
            ("The crisis is real and remains the same from opening to ending.",
             "Choices affect means, consequences, reputation and routes.",
             "The same characters inhabit the world between cutscenes."),
            ("The world survives through stewardship.",
             "The world survives through discovery.",
             "The world survives through independence."),
            ("Foundations", "Conflict", "Turning Point", "Consequences"),
        ), tuple(scenes), tuple(quest_items), "scene_00",
    )


def compile_director_blueprint(doc: dict, *, human_reviewed: bool) -> DirectorWorld:
    if human_reviewed is not True:
        raise DirectorError("full-scene human author approval required")
    def obj(typ, value):
        if type(value) is not dict or set(value) != {
            f.name for f in fields(typ)
        }:
            raise DirectorError("scene data has missing, extra or script-bearing properties")
        return value
    def parse_scene(x):
        d = obj(Scene, x)
        return Scene(**{k: d[k] for k in (
            "key", "region", "title", "setting", "camera", "lighting",
            "weather", "music", "style",
        )},
        cast=tuple(d["cast"]), props=tuple(d["props"]), links=tuple(d["links"]),
        affordances=tuple(Affordance(**obj(Affordance, a))
                          for a in d["affordances"]),
        cutscenes=tuple(Cutscene(
            **{k: obj(Cutscene, cut)[k] for k in (
                "key", "title", "skippable", "trigger",
            )},
            cues=tuple(Cue(**obj(Cue, cue)) for cue in cut["cues"]),
        ) for cut in d["cutscenes"]))
    def parse_arc(x):
        d = obj(QuestArc, x)
        return QuestArc(**{k: d[k] for k in (
            "key", "name", "scope", "archetype", "theme", "premise",
            "narrative_cause", "consequences", "placement",
            "repeat_limit", "ending_axis",
        )}, requires_quests=tuple(d["requires_quests"]),
        stages=tuple(QuestStage(
            **{k: obj(QuestStage, s)[k] for k in (
                "key", "title", "lore", "time_target",
                "cutscene_on_start", "cutscene_on_complete",
            )},
            scene_ids=tuple(s["scene_ids"]),
            solutions=tuple(Solution(
                **{k: obj(Solution, z)[k] for k in (
                    "key", "creativity", "outcome_flag",
                )},
                required=tuple(Parameter(**obj(Parameter, p))
                               for p in z["required"]),
            ) for z in s["solutions"]),
            optional=tuple(Parameter(**obj(Parameter, p))
                           for p in s["optional"]),
        ) for s in d["stages"]))
    if type(doc) is not dict or set(doc) != {
        "schema", "project_id", "seed", "bible", "scenes", "quests", "starting_scene"
    } or doc["schema"] != "skeleton.game_builder.director_world.v1":
        raise DirectorError("invalid authored director schema")
    b = obj(NarrativeBible, doc["bible"])
    return DirectorWorld(
        doc["project_id"], doc["seed"],
        NarrativeBible(
            b["theme"], b["opening"], b["invariant_goal"],
            tuple(b["canonical_facts"]), tuple(b["ending_outcomes"]),
            tuple(b["lore_epochs"]),
        ),
        tuple(parse_scene(s) for s in doc["scenes"]),
        tuple(parse_arc(q) for q in doc["quests"]),
        doc["starting_scene"],
    )


def read_director_blueprint(source: str | Path, *, human_reviewed: bool):
    f = Path(source)
    if f.is_symlink() or not f.is_file() or f.stat().st_size > 1_200_000:
        raise DirectorError("director needs a regular local JSON below 1.2 MB")
    raw = f.read_bytes()
    try:
        doc = json.loads(raw.decode("utf-8", "strict"),
                         object_pairs_hook=_no_duplicate_keys,
                         parse_constant=_json_number_reject)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise DirectorError("ambiguous original director JSON rejected") from exc
    return compile_director_blueprint(doc, human_reviewed=human_reviewed)


__all__ = [
    "forge_director", "compile_director_blueprint",
    "read_director_blueprint", "METHODS",
]
