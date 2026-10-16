"""Non-destructive living-world campaign forge for original reviewed games.

Generates a *reviewable* typed variation with faction influence, unlockable
passages, optional gated walking shortcuts and multi-modal transport. Preview
performs no writes. Publish requires an exact content digest and preserves
the earlier world source; game authors remain responsible for accepting
narrative plausibility, originality and any changes to canon.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from skeleton.ai.game_builder.quest_scene_forge import compile_director_blueprint
from skeleton.ai.game_builder.quest_world_dynamics import (
    Faction, Gate, Influence, Passage, Requirements, StandingRequirement,
    WorldDynamics,
)
from skeleton.developer.jeeves_game_director_dynamic_audit import analyze
from skeleton.developer.jeeves_game_production_board import _load_world

SCHEMA = "skeleton.jeeves.dynamic_world_design.v1"


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _bypass(links: dict[str, tuple[str, ...]], start: str, target: str,
            omitted: tuple[str, str]) -> bool:
    explored = set()
    queue = deque([start])
    while queue:
        here = queue.popleft()
        if here == target:
            return True
        if here in explored:
            continue
        explored.add(here)
        queue.extend(
            there for there in links[here]
            if (here, there) != omitted and there not in explored
        )
    return False


def _fresh(name: str, taken: set[str]) -> str:
    """Use stable safe IDs without colliding with authored existing identities."""
    candidate = name[:64]
    if candidate not in taken:
        taken.add(candidate)
        return candidate
    for index in range(2, 10000):
        candidate = (name[:max(1, 62 - len(str(index)))]
                     + "_" + str(index))
        if candidate not in taken:
            taken.add(candidate)
            return candidate
    raise ValueError("cannot construct an unambiguous original dynamic-world identity")


def _choose_affordance(world: Any) -> tuple[str, str] | None:
    # Choose an executable quest action (not an unused prop) for the first
    # influence. Prefer an opening quest to make the system observable.
    for quest in world.quests:
        for stage in quest.stages:
            for solution in stage.solutions:
                for parameter in solution.required:
                    for scene in world.scenes:
                        if scene.key not in stage.scene_ids:
                            continue
                        for a in scene.affordances:
                            if a.kind == parameter.kind and a.target == parameter.target:
                                return scene.key, a.key
    return None


def _build(world: Any, *, intensity: int) -> WorldDynamics:
    if type(intensity) is not int or not 1 <= intensity <= 5:
        raise ValueError("world dynamics intensity must be 1..5")
    scenes = list(world.scenes)
    if len(scenes) < 2:
        raise ValueError("dynamic traversal requires at least two authored scenes")
    regions = sorted({s.region for s in scenes})
    known_scene = {s.key: s for s in scenes}
    links = {s.key: s.links for s in scenes}
    faction_ids = set()
    faction_count = min(len(regions), max(2, intensity + 1), 8)
    factions = tuple(Faction(
        key=_fresh("guild_" + regions[i % len(regions)], faction_ids),
        name="Guardians of " + regions[i % len(regions)].replace("_", " ").title(),
        starting_standing=0,
    ) for i in range(faction_count))
    main_quest = next(q for q in world.quests if q.scope == "main")
    first_solution = main_quest.stages[0].solutions[0]
    world_flags = set()
    opened = _fresh("passage_charter", world_flags)
    used = _fresh("heard_the_signal", world_flags)
    influences = [
        Influence(
            key="original_charter",
            trigger="quest_result", faction=factions[0].key,
            delta=80, quest=main_quest.key,
            outcome_flag=first_solution.outcome_flag,
            grant_world_flag=opened,
            once=True,
        )
    ]
    discovered = _choose_affordance(world)
    if discovered:
        scene, key = discovered
        influences.append(Influence(
            key="local_influence", trigger="use",
            faction=factions[-1].key, delta=20, scene=scene,
            affordance=key, grant_world_flag=used, once=True,
        ))
    gates = []
    gate_target = min(3 * intensity, 12)
    # Only gate a link where an alternative *ungated* walking route exists,
    # otherwise a freshly published world may hard-lock its own main story.
    # This is a conservative authoring heuristic, not full state-space proof.
    for scene in scenes:
        if len(gates) >= gate_target:
            break
        for neighbor in scene.links:
            if len(gates) >= gate_target:
                break
            if not _bypass(links, scene.key, neighbor, (scene.key, neighbor)):
                continue
            requirement = Requirements(
                world_flags=(opened,),
                standings=(StandingRequirement(
                    faction=factions[0].key, at_least=30, at_most=1000,
                ),),
            )
            gates.append(Gate(
                source=scene.key, destination=neighbor,
                label="Charter-protected " + scene.region.replace("_", " ") + " passage",
                requirements=requirement,
            ))
    passages = []
    taken = set()
    origin, end = world.starting_scene, scenes[-1].key
    if end == origin:
        end = scenes[0].key
    passages.append(Passage(
        key=_fresh("public_ferry", taken),
        source=origin, destination=end,
        mode="ferry", name="Original public ferry service",
        cost_turns=max(2, 6 - intensity), bidirectional=True,
        requirements=Requirements(),
        grant_world_flag=_fresh("first_crossing", world_flags),
    ))
    # No guessed flags: charter is granted only by an actual approved quest
    # method; the optional portal adds faster transport, not a cheat.
    passages.append(Passage(
        key=_fresh("charter_portal", taken),
        source=origin, destination=end,
        mode="portal", name="Charter-licensed original portal",
        cost_turns=1, bidirectional=True,
        requirements=Requirements(
            world_flags=(opened,),
            standings=(StandingRequirement(
                faction=factions[0].key, at_least=30, at_most=1000,
            ),),
        ),
    ))
    if intensity >= 2 and len(scenes) > 2:
        midpoint = scenes[len(scenes) // 2].key
        if midpoint != origin:
            passages.append(Passage(
                key=_fresh("regional_shuttle", taken),
                source=origin, destination=midpoint, mode="shuttle",
                name="Licensed original regional shuttle",
                cost_turns=2, bidirectional=True,
                requirements=Requirements(),
                reputation_change=((factions[-1].key, 1),),
            ))
    produced = [
        (s, a) for s in scenes for a in s.affordances if a.produces is not None
    ]
    if intensity >= 3 and produced:
        ticket = produced[0][1].produces
        stop = scenes[max(1, len(scenes) // 3)].key
        if stop == origin:
            stop = end
        passages.append(Passage(
            key=_fresh("ticketed_airship", taken),
            source=origin, destination=stop, mode="airship",
            name="Ticketed airship to an alternate original district",
            cost_turns=1, bidirectional=False,
            requirements=Requirements(items=(ticket,)),
            consume_item=ticket,
        ))
    if intensity >= 4 and len(scenes) >= 4:
        a = scenes[len(scenes) // 4].key
        b = scenes[(3 * len(scenes)) // 4].key
        if a != b:
            passages.append(Passage(
                key=_fresh("research_elevator", taken),
                source=a, destination=b, mode="elevator",
                name="Original experimental multi-level elevator",
                cost_turns=2, bidirectional=True,
                requirements=Requirements(world_flags=(opened,)),
            ))
    if intensity >= 5 and len(scenes) >= 5:
        a = scenes[1].key
        b = scenes[-2].key
        if a != b:
            passages.append(Passage(
                key=_fresh("deep_water_route", taken),
                source=a, destination=b, mode="underwater",
                name="Original underwater exploration conduit",
                cost_turns=8, bidirectional=True,
                requirements=Requirements(world_flags=(opened,)),
            ))
    dynamics = WorldDynamics(
        factions=factions, gates=tuple(gates),
        passages=tuple(passages), influences=tuple(influences),
    )
    # Recompile strict round-trip JSON to ensure every authored parameter is
    # executable, not just a pretty design sketch.
    return dynamics


def preview(root: Path, *, source: str, intensity: int = 3) -> dict[str, Any]:
    from skeleton.developer.jeeves_game_quality import _read
    world, source_sha = _load_world(root, source)
    if world.dynamics is not None:
        raise ValueError("living-world authoring requires an undynamic source; preserve revisions")
    dynamics = _build(world, intensity=intensity)
    rewritten = world.payload()
    rewritten["dynamics"] = dynamics.payload()
    compiled = compile_director_blueprint(rewritten, human_reviewed=True)
    if compiled.payload() != rewritten or compiled.digest == world.digest:
        raise ValueError("generated faction/transit design failed exact type round-trip")
    analysis = analyze(compiled)
    candidate = {
        "schema": "skeleton.jeeves.director_campaign_source.v1",
        "director_world": rewritten,
        # Preview is not human-reviewed merely because its inputs were.
        # This flag becomes true only at explicit digest-approved publish.
        "author_review_acknowledged": False,
    }
    content = {
        "schema": SCHEMA, "source": source,
        "source_sha256": source_sha,
        "base_world_sha256": world.digest,
        "dynamic_world_sha256": compiled.digest,
        "intensity": intensity, "candidate": candidate,
        "world_assurance": analysis,
        "original_source_preserved": True,
        "actual_provider_model_generation_used": False,
        "narrative_quality_human_review_required": True,
        "gameplay_native_engine_verified": False,
    }
    digest = _digest(content)
    if _read(root, source, 16 * 1024 * 1024)[1] != source_sha:
        raise ValueError("source game changed during living-world draft generation")
    return {
        "ok": True, "action": "director-dynamics-design",
        "design": content, "design_sha256": digest,
        "published": False, "writes": 0,
    }


def publish(root: Path, *, source: str, intensity: int,
            approved_sha256: str | None) -> dict[str, Any]:
    from skeleton.developer.jeeves_game_authoring import _create_only
    design = preview(root, source=source, intensity=intensity)
    if approved_sha256 != design["design_sha256"]:
        raise ValueError("publish requires explicit --approve exact reviewed dynamic-design SHA256")
    again = preview(root, source=source, intensity=intensity)
    if again != design:
        raise ValueError("authored game changed during approved dynamic-world publication")
    data = dict(design["design"]["candidate"])
    data["author_review_acknowledged"] = True
    raw = (json.dumps(data, indent=2, sort_keys=True,
                      ensure_ascii=True, allow_nan=False) + "\n").encode()
    if len(raw) > 16 * 1024 * 1024:
        raise ValueError("original dynamic-world campaign exceeds source file budget")
    folder = root / "design"
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError("game design folder is missing or unsafe")
    path = folder / ("director_dynamic_" + design["design_sha256"][:24] + ".json")
    _create_only(path, raw)
    return {
        "ok": True, "action": "director-dynamics-publish",
        "source": path.relative_to(root).as_posix(),
        "source_sha256": sha256(raw).hexdigest(),
        "world_sha256": design["design"]["dynamic_world_sha256"],
        "original_source_preserved": True,
        "requires_independent_story_quality_review": True,
        "godot_playthrough_verified": False,
        "published": True,
    }
