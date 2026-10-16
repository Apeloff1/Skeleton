"""Executable quest direction for original games, not rigid type-to-task tables.

A designer controls every scene, its affordances, cast, staging and timeline.
Stages accept OR-of-AND victory parameter sets, with optional goals, replay-
measured speed/novelty bonuses and authored consequence flags. All actions are
checked against exact declared scene affordances; no scripts, arbitrary events,
asset file reads or provider/network operations are trusted.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
from collections import deque
from typing import Sequence
import random
import re

from .contracts import canonical_digest
from .quest_world_dynamics import (
    WorldDynamics, WorldState, initial as initial_dynamics,
    allowed_foot_travel, offered_passages, apply_changes,
    effects_for_use, effects_for_results,
)

MAX_SCENES = 128
MAX_QUESTS = 256
MAX_STAGES = 12
MAX_EVENTS = 8192
MAX_TRACKS = 48
MAX_CUES = 128

ARCHETYPES = frozenset((
    "main_story", "main_chain", "side_arc", "side_chain", "regional_story",
    "regional_chain", "proficiency", "attunement", "profession", "rival",
    "rival_story", "dungeoneering", "infusion", "repeatable", "escort_path",
    "escort_leash", "escort_introduction", "acquisition", "gathering",
    "courier", "combat", "rival_combat", "timed_rival_combat", "timed_combat",
    "survival_waves", "reinforcement", "exploration", "investigation",
    "negotiation", "diplomacy", "crafting", "repair", "construction",
    "defense", "rescue", "stealth", "puzzle", "navigation", "ritual",
    "resource_management", "companionship", "restoration", "discovery",
    "ecology", "trading", "reputation", "mystery", "trial", "training",
    "world_event", "epilogue",
))
ACTION_TYPES = frozenset((
    "inspect", "talk", "trade", "gather", "deliver", "craft", "repair",
    "build", "fight", "pacify", "negotiate", "sneak", "protect", "reinforce",
    "survive", "heal", "research", "attune", "infuse", "train", "solve",
    "escort_follow", "escort_leash", "escort_introduce", "travel", "activate",
    "interact", "discover", "wait",
))
CUE_TYPES = frozenset((
    "camera_cut", "camera_pan", "camera_track", "camera_dolly", "camera_zoom",
    "camera_shake", "focus", "subtitle", "dialogue", "voice_cue",
    "music_cue", "sound_cue", "ambient_cue", "lighting", "weather",
    "color_grade", "fade", "wipe", "actor_enter", "actor_exit",
    "actor_move", "actor_pose", "actor_emote", "animation", "particle",
    "prop_state", "ui_prompt", "objective_reveal", "choice_prompt",
    "slow_motion", "pause", "resume", "hud_visibility",
))
SCOPES = frozenset(("main", "arc", "side", "region", "rival", "repeatable"))
METHOD_RANKS = frozenset(("ordinary", "creative", "ingenious"))
_V = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class DirectorError(ValueError):
    """Unsupported authored direction or simulated action."""


def _id(value: object) -> str:
    if not isinstance(value, str) or _V.fullmatch(value) is None:
        raise DirectorError("scene, quest, resource and flag IDs must be safe")
    return value


def _label(value: object, max_length: int = 300) -> str:
    if (not isinstance(value, str) or not 1 <= len(value) <= max_length
            or value != value.strip() or any(ord(ch) < 32 for ch in value)):
        raise DirectorError("authored text must be bounded and printable")
    value.encode("utf-8", "strict")
    return value


def _count(n: object, low: int, high: int) -> int:
    if type(n) is not int or not low <= n <= high:
        raise DirectorError("invalid resource, timing or quest count")
    return n


@dataclass(frozen=True, slots=True)
class Cue:
    at: int  # animation timeline milliseconds
    kind: str
    target: str
    value: str
    duration: int = 0
    easing: str = "linear"

    def __post_init__(self):
        _count(self.at, 0, 120_000)
        _count(self.duration, 0, 120_000)
        if self.at + self.duration > 120_000:
            raise DirectorError("cinematic exceeds two-minute budget")
        if self.kind not in CUE_TYPES or self.easing not in {
            "linear", "ease_in", "ease_out", "ease_in_out", "step"
        }:
            raise DirectorError("unknown typed cutscene cue or easing")
        _id(self.target)
        _label(self.value, 500)

    def payload(self):
        return dict(at=self.at, kind=self.kind, target=self.target,
                    value=self.value, duration=self.duration, easing=self.easing)


@dataclass(frozen=True, slots=True)
class Cutscene:
    key: str
    title: str
    skippable: bool
    cues: tuple[Cue, ...]
    trigger: str = "on_enter"

    def __post_init__(self):
        _id(self.key)
        _label(self.title, 120)
        if type(self.skippable) is not bool or self.trigger not in {
            "on_enter", "on_exit", "on_quest_start", "on_stage_complete",
            "on_quest_complete", "on_ending"
        }:
            raise DirectorError("invalid cutscene trigger or skip policy")
        if not isinstance(self.cues, tuple) or not 1 <= len(self.cues) <= MAX_CUES:
            raise DirectorError("cutscene needs 1 to 128 typed timeline cues")
        if any(not isinstance(c, Cue) for c in self.cues) or tuple(
            sorted(self.cues, key=lambda c: c.at)
        ) != self.cues:
            raise DirectorError("cutscene cues must be sorted chronologically")

    def payload(self):
        return dict(key=self.key, title=self.title, skippable=self.skippable,
                    trigger=self.trigger, cues=[c.payload() for c in self.cues])


@dataclass(frozen=True, slots=True)
class Affordance:
    """An actual action available at a scene: bounded cost, evidence, resources."""
    key: str
    kind: str
    target: str
    effort: int = 1
    quality: str = "ordinary"
    consumes: str | None = None
    produces: str | None = None
    proximity: int = 0  # escort leash steps, zero for other actions
    danger: int = 0

    def __post_init__(self):
        _id(self.key)
        if self.kind not in ACTION_TYPES:
            raise DirectorError("unsupported player action type")
        _id(self.target)
        _count(self.effort, 1, 60)
        _count(self.proximity, 0, 8)
        _count(self.danger, 0, 9)
        if self.quality not in METHOD_RANKS:
            raise DirectorError("unrecognized original solution quality")
        if self.consumes is not None:
            _id(self.consumes)
        if self.produces is not None:
            _id(self.produces)
        if self.kind != "escort_leash" and self.proximity:
            raise DirectorError("leash ranges only apply to paired escort actions")
        if self.kind == "escort_leash" and not 1 <= self.proximity <= 8:
            raise DirectorError("escort leash requires real noncolliding range constraint")

    def payload(self):
        return dict(key=self.key, kind=self.kind, target=self.target,
                    effort=self.effort, quality=self.quality,
                    consumes=self.consumes, produces=self.produces,
                    proximity=self.proximity, danger=self.danger)


@dataclass(frozen=True, slots=True)
class Scene:
    key: str
    region: str
    title: str
    setting: str
    camera: str
    lighting: str
    weather: str
    music: str
    cast: tuple[str, ...]
    props: tuple[str, ...]
    affordances: tuple[Affordance, ...]
    cutscenes: tuple[Cutscene, ...] = ()
    links: tuple[str, ...] = ()
    style: str = "original"

    def __post_init__(self):
        _id(self.key)
        _id(self.region)
        for name in (self.title, self.setting, self.camera, self.lighting,
                     self.weather, self.music, self.style):
            _label(name, 500)
        if not 1 <= len(self.affordances) <= 64 or not all(
            isinstance(a, Affordance) for a in self.affordances
        ):
            raise DirectorError("scene requires bounded runnable action affordances")
        for values in (self.cast, self.props, self.links):
            if not isinstance(values, tuple) or len(values) > 64:
                raise DirectorError("scene cast, props or links exceed budget")
            for value in values:
                _id(value)
            if len(set(values)) != len(values):
                raise DirectorError("duplicate authored scene identity")
        if len({a.key for a in self.affordances}) != len(self.affordances):
            raise DirectorError("duplicate action IDs within a scene")
        if len(self.cutscenes) > 16 or any(not isinstance(c, Cutscene) for c in self.cutscenes):
            raise DirectorError("scene cutscene budget exceeded")
        if len({c.key for c in self.cutscenes}) != len(self.cutscenes):
            raise DirectorError("cutscene identities must be unique in each scene")

    def payload(self):
        return dict(key=self.key, region=self.region, title=self.title,
                    setting=self.setting, camera=self.camera, lighting=self.lighting,
                    weather=self.weather, music=self.music, style=self.style,
                    cast=list(self.cast), props=list(self.props), links=list(self.links),
                    affordances=[a.payload() for a in self.affordances],
                    cutscenes=[c.payload() for c in self.cutscenes])


@dataclass(frozen=True, slots=True)
class Parameter:
    """An evidence condition; all in an approach required, approaches are OR."""
    kind: str
    target: str
    count: int = 1

    def __post_init__(self):
        if self.kind not in ACTION_TYPES:
            raise DirectorError("unsupported victory predicate")
        _id(self.target)
        _count(self.count, 1, 100)

    def payload(self):
        return dict(kind=self.kind, target=self.target, count=self.count)


@dataclass(frozen=True, slots=True)
class Solution:
    key: str
    required: tuple[Parameter, ...]
    creativity: int = 0
    outcome_flag: str = "path_original"

    def __post_init__(self):
        _id(self.key)
        if not isinstance(self.required, tuple) or not 1 <= len(self.required) <= 8:
            raise DirectorError("solution requires 1 to 8 measurable conditions")
        if any(not isinstance(x, Parameter) for x in self.required):
            raise DirectorError("invalid victory condition type")
        _count(self.creativity, 0, 100)
        _id(self.outcome_flag)

    def payload(self):
        return dict(key=self.key, required=[p.payload() for p in self.required],
                    creativity=self.creativity, outcome_flag=self.outcome_flag)


@dataclass(frozen=True, slots=True)
class QuestStage:
    key: str
    title: str
    lore: str
    scene_ids: tuple[str, ...]
    solutions: tuple[Solution, ...]
    optional: tuple[Parameter, ...] = ()
    time_target: int = 12
    cutscene_on_start: str | None = None
    cutscene_on_complete: str | None = None

    def __post_init__(self):
        _id(self.key)
        _label(self.title, 150)
        _label(self.lore, 1200)
        if (not isinstance(self.scene_ids, tuple)
                or not 1 <= len(self.scene_ids) <= 8 or
                len(set(self.scene_ids)) != len(self.scene_ids)):
            raise DirectorError("stage must reference 1 to 8 distinct scenes")
        for key in self.scene_ids:
            _id(key)
        if not isinstance(self.solutions, tuple) or not 1 <= len(self.solutions) <= 8:
            raise DirectorError("stage needs multiple viable methods or one proof")
        if any(not isinstance(x, Solution) for x in self.solutions):
            raise DirectorError("invalid victory solution")
        if len(set(x.key for x in self.solutions)) != len(self.solutions):
            raise DirectorError("duplicate approach ID")
        if not isinstance(self.optional, tuple) or len(self.optional) > 16:
            raise DirectorError("optional victory budget exceeded")
        if any(not isinstance(x, Parameter) for x in self.optional):
            raise DirectorError("invalid optional victory")
        _count(self.time_target, 1, 1000)
        for key in (self.cutscene_on_start, self.cutscene_on_complete):
            if key is not None:
                _id(key)

    def payload(self):
        return dict(key=self.key, title=self.title, lore=self.lore,
                    scene_ids=list(self.scene_ids),
                    solutions=[s.payload() for s in self.solutions],
                    optional=[p.payload() for p in self.optional],
                    time_target=self.time_target,
                    cutscene_on_start=self.cutscene_on_start,
                    cutscene_on_complete=self.cutscene_on_complete)


@dataclass(frozen=True, slots=True)
class QuestArc:
    key: str
    name: str
    scope: str
    archetype: str
    theme: str
    premise: str
    narrative_cause: str
    consequences: str
    stages: tuple[QuestStage, ...]
    requires_quests: tuple[str, ...] = ()
    placement: str = "story"
    repeat_limit: int = 1
    ending_axis: str = "none"

    def __post_init__(self):
        _id(self.key)
        for name in (self.name, self.theme, self.premise, self.narrative_cause,
                     self.consequences):
            _label(name, 1200)
        if self.scope not in SCOPES or self.archetype not in ARCHETYPES:
            raise DirectorError("unsupported quest scope or archetype")
        if not isinstance(self.stages, tuple) or not 1 <= len(self.stages) <= MAX_STAGES:
            raise DirectorError("multi-stage quest supports up to 12 real stages")
        if any(not isinstance(s, QuestStage) for s in self.stages):
            raise DirectorError("quest contains invalid stage")
        if len(set(s.key for s in self.stages)) != len(self.stages):
            raise DirectorError("quest stage IDs must be unique")
        for q in self.requires_quests:
            _id(q)
        if len(set(self.requires_quests)) != len(self.requires_quests):
            raise DirectorError("duplicate quest prerequisite")
        if self.placement not in {"story", "seeded", "regional", "player_choice"}:
            raise DirectorError("invalid bounded quest placement policy")
        _count(self.repeat_limit, 1, 32)
        if self.scope != "repeatable" and self.repeat_limit != 1:
            raise DirectorError("only repeatable quests can repeat")
        if self.ending_axis not in {"none", "stewardship", "discovery", "independence"}:
            raise DirectorError("unsupported narrative ending axis")

    def payload(self):
        return dict(key=self.key, name=self.name, scope=self.scope,
                    archetype=self.archetype, theme=self.theme, premise=self.premise,
                    narrative_cause=self.narrative_cause,
                    consequences=self.consequences,
                    stages=[s.payload() for s in self.stages],
                    requires_quests=list(self.requires_quests),
                    placement=self.placement, repeat_limit=self.repeat_limit,
                    ending_axis=self.ending_axis)


@dataclass(frozen=True, slots=True)
class NarrativeBible:
    theme: str
    opening: str
    invariant_goal: str
    canonical_facts: tuple[str, ...]
    ending_outcomes: tuple[str, str, str]
    lore_epochs: tuple[str, ...] = ()

    def __post_init__(self):
        for text in (self.theme, self.opening, self.invariant_goal,
                     *self.canonical_facts, *self.ending_outcomes, *self.lore_epochs):
            _label(text, 1200)
        if not 1 <= len(self.canonical_facts) <= 32:
            raise DirectorError("must establish at least one canonical story fact")
        if len(self.lore_epochs) > 32:
            raise DirectorError("bounded narrative epoch index required")

    def payload(self):
        return dict(theme=self.theme, opening=self.opening,
                    invariant_goal=self.invariant_goal,
                    canonical_facts=list(self.canonical_facts),
                    ending_outcomes=list(self.ending_outcomes),
                    lore_epochs=list(self.lore_epochs))


@dataclass(frozen=True, slots=True)
class DirectorWorld:
    project_id: str
    seed: int
    bible: NarrativeBible
    scenes: tuple[Scene, ...]
    quests: tuple[QuestArc, ...]
    starting_scene: str
    dynamics: WorldDynamics | None = None

    def __post_init__(self):
        _id(self.project_id)
        _count(self.seed, 0, 2**63 - 1)
        _id(self.starting_scene)
        if not isinstance(self.bible, NarrativeBible):
            raise DirectorError("canonical narrative foundation required")
        if not 1 <= len(self.scenes) <= MAX_SCENES or not 1 <= len(self.quests) <= MAX_QUESTS:
            raise DirectorError("game scenes and quests exceed bounded allocation")
        scene_map = {s.key: s for s in self.scenes}
        quest_map = {q.key: q for q in self.quests}
        if (len(scene_map) != len(self.scenes) or len(quest_map) != len(self.quests)
                or self.starting_scene not in scene_map):
            raise DirectorError("missing original scene or repeated identifier")
        if any(not isinstance(s, Scene) for s in self.scenes) or any(
            not isinstance(q, QuestArc) for q in self.quests
        ):
            raise DirectorError("typed original authored content required")
        # Travel is through explicit bidirectional scene entrances. Worlds can
        # contain optional isolated set pieces only if not referenced by quests.
        for scene in self.scenes:
            if any(link not in scene_map for link in scene.links):
                raise DirectorError("scene exit leads to an unknown environment")
            for link in scene.links:
                if scene.key not in scene_map[link].links:
                    raise DirectorError("scene entrances must be bidirectional")
        known = {self.starting_scene}
        pending = deque([self.starting_scene])
        while pending:
            for neighbor in scene_map[pending.popleft()].links:
                if neighbor not in known:
                    known.add(neighbor)
                    pending.append(neighbor)
        if known != set(scene_map):
            raise DirectorError("every authored scene must be navigable")
        for quest in self.quests:
            if quest.key in quest.requires_quests or any(
                dep not in quest_map for dep in quest.requires_quests
            ):
                raise DirectorError("quest dependency references another project or itself")
            for stage in quest.stages:
                if any(scene not in scene_map for scene in stage.scene_ids):
                    raise DirectorError("stage references unavailable authored scene")
                available = {(a.kind, a.target) for sid in stage.scene_ids
                             for a in scene_map[sid].affordances}
                for solution in stage.solutions:
                    if any((p.kind, p.target) not in available for p in solution.required):
                        raise DirectorError("victory method cannot actually execute in its scenes")
                for p in stage.optional:
                    if (p.kind, p.target) not in available:
                        raise DirectorError("optional goal has no real executable affordance")
                for key in (stage.cutscene_on_start, stage.cutscene_on_complete):
                    if key is not None and not any(
                        cut.key == key for sid in stage.scene_ids
                        for cut in scene_map[sid].cutscenes
                    ):
                        raise DirectorError("quest cutscene has no authored scene/timeline")
        visiting, resolved = set(), set()
        def visit(key):
            if key in visiting:
                raise DirectorError("story arc prerequisites contain a dependency cycle")
            if key in resolved:
                return
            visiting.add(key)
            for dep in quest_map[key].requires_quests:
                visit(dep)
            visiting.remove(key)
            resolved.add(key)
        for key in quest_map:
            visit(key)
        if not any(q.scope == "main" for q in self.quests):
            raise DirectorError("main story with invariant global goal required")
        if not any(q.ending_axis != "none" for q in self.quests):
            raise DirectorError("main story must have meaningful choice-aligned outcome")
        if self.dynamics is not None:
            if not isinstance(self.dynamics, WorldDynamics):
                raise DirectorError("original-world dynamics must be typed")
            # Author permission paths MUST resolve to the same canonical
            # game graph, quest scripts and available real affordances.
            for gate in self.dynamics.gates:
                if (gate.source not in scene_map or gate.destination not in
                        scene_map[gate.source].links):
                    raise DirectorError("gate references a nonexistent walking link")
            for route in self.dynamics.passages:
                if (route.source not in scene_map or route.destination not in scene_map):
                    raise DirectorError("transit references an unbuilt scene")
            for record in self.dynamics.influences:
                if record.trigger == "use":
                    scene = scene_map.get(record.scene)
                    if scene is None or record.affordance not in {
                            a.key for a in scene.affordances}:
                        raise DirectorError("reputation influence has no actual interaction")
                else:
                    quest = quest_map.get(record.quest)
                    if quest is None:
                        raise DirectorError("reputation effect references unknown quest")
                    if record.outcome_flag is not None and not any(
                            method.outcome_flag == record.outcome_flag
                            for stage in quest.stages for method in stage.solutions):
                        raise DirectorError("faction outcome does not occur in authored story")
            known_items = {
                action.produces for scene in self.scenes
                for action in scene.affordances if action.produces
            }
            outcome_flags = {
                method.outcome_flag for quest in self.quests
                for stage in quest.stages for method in stage.solutions
            }
            possible_world_flags = {
                item.grant_world_flag for item in
                (*self.dynamics.passages, *self.dynamics.influences)
                if item.grant_world_flag is not None
            }
            for requirements in (
                    *(g.requirements for g in self.dynamics.gates),
                    *(p.requirements for p in self.dynamics.passages)):
                if not set(requirements.quests).issubset(quest_map):
                    raise DirectorError("travel condition references an unknown quest")
                if not set(requirements.items).issubset(known_items):
                    raise DirectorError("required ticket/key cannot be earned in this game")
                if not set(requirements.flags).issubset(outcome_flags):
                    raise DirectorError("conditional travel references an unknown ending flag")
                if not set(requirements.world_flags).issubset(possible_world_flags):
                    raise DirectorError("conditional travel requires an unproducible world flag")

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        result = dict(schema="skeleton.game_builder.director_world.v1",
                      project_id=self.project_id, seed=self.seed,
                      bible=self.bible.payload(),
                      scenes=[s.payload() for s in self.scenes],
                      quests=[q.payload() for q in self.quests],
                      starting_scene=self.starting_scene)
        # Critical backward compatibility: legacy worlds keep exactly the
        # same canonical source hash and all existing session receipt hashes.
        if self.dynamics is not None:
            result["dynamics"] = self.dynamics.payload()
        return result


@dataclass(frozen=True, slots=True)
class DirectorAction:
    kind: str
    key: str
    scene: str

    def __post_init__(self):
        if self.kind not in {"travel", "use", "wait", "transit"}:
            raise DirectorError("invalid action kind")
        _id(self.key)
        _id(self.scene)

    def payload(self):
        return dict(kind=self.kind, key=self.key, scene=self.scene)


@dataclass(frozen=True, slots=True)
class DirectorResult:
    quest: str
    stage: str
    approach: str
    turns: int
    speed_bonus: int
    creativity_bonus: int
    optional_bonus: int
    score: int
    consequence: str
    lore_entry: str

    def payload(self):
        return dict(quest=self.quest, stage=self.stage, approach=self.approach,
                    turns=self.turns, speed_bonus=self.speed_bonus,
                    creativity_bonus=self.creativity_bonus,
                    optional_bonus=self.optional_bonus, score=self.score,
                    consequence=self.consequence, lore_entry=self.lore_entry)


@dataclass(frozen=True, slots=True)
class DirectorState:
    world_digest: str
    scene: str
    turn: int
    stage_index: tuple[tuple[str, int], ...]
    complete: tuple[str, ...]
    records: tuple[tuple[str, str, str, int], ...] # quest,stage,kind:target,count
    acquired: tuple[str, ...]
    results: tuple[DirectorResult, ...]
    cutscenes_seen: tuple[str, ...]
    narrative_flags: tuple[str, ...]
    world_state: WorldState | None = None

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        result = dict(world_digest=self.world_digest, scene=self.scene,
                      turn=self.turn, stage_index=[list(x) for x in self.stage_index],
                      complete=list(self.complete), records=[list(x) for x in self.records],
                      acquired=list(self.acquired),
                      results=[r.payload() for r in self.results],
                      cutscenes_seen=list(self.cutscenes_seen),
                      narrative_flags=list(self.narrative_flags))
        if self.world_state is not None:
            result["world_state"] = self.world_state.payload()
        return result


def director_initial(world: DirectorWorld) -> DirectorState:
    if not isinstance(world, DirectorWorld):
        raise DirectorError("typed director world required")
    return DirectorState(
        world.digest, world.starting_scene, 0,
        tuple((q.key, 0) for q in world.quests), (), (), (), (), (), (),
        initial_dynamics(world.dynamics) if world.dynamics is not None else None,
    )


def _progress(world: DirectorWorld, state: DirectorState):
    if not isinstance(state, DirectorState) or state.world_digest != world.digest:
        raise DirectorError("foreign narrative history")
    # Long-form projects accumulate any number of accepted turns across
    # bounded replay slices. MAX_EVENTS guards an individual replay invocation,
    # never the lifetime of a game or its verified progress.
    qmap = {q.key: q for q in world.quests}
    return qmap, dict(state.stage_index)


def available_director_actions(world: DirectorWorld, state: DirectorState) -> tuple[DirectorAction, ...]:
    quest_map, progress = _progress(world, state)
    here = next((s for s in world.scenes if s.key == state.scene), None)
    if here is None:
        raise DirectorError("story state occupies an absent scene")
    usable = set()
    for quest in world.quests:
        idx = progress[quest.key]
        if idx >= len(quest.stages) or not set(quest.requires_quests).issubset(state.complete):
            continue
        stage = quest.stages[idx]
        if here.key in stage.scene_ids:
            usable.update((a.kind, a.target) for solution in stage.solutions
                          for p in solution.required for a in here.affordances
                          if (a.kind, a.target) == (p.kind, p.target))
            usable.update((p.kind, p.target) for p in stage.optional)
    actions = [
        DirectorAction("travel", link, here.key) for link in here.links
        if world.dynamics is None
        or allowed_foot_travel(world.dynamics, state, link)
    ]
    if world.dynamics is not None:
        actions.extend(
            DirectorAction("transit", passage.key, here.key)
            for passage in offered_passages(world.dynamics, state)
        )
    for a in here.affordances:
        if (a.kind, a.target) in usable and (
            a.consumes is None or a.consumes in state.acquired
        ):
            actions.append(DirectorAction("use", a.key, here.key))
    actions.append(DirectorAction("wait", "wait", here.key))
    return tuple(actions)


def director_step(world: DirectorWorld, state: DirectorState, action: DirectorAction) -> DirectorState:
    quest_map, progress = _progress(world, state)
    if action not in available_director_actions(world, state):
        raise DirectorError("action unavailable in current authored scene/quest stage")
    here = next(s for s in world.scenes if s.key == state.scene)
    if action.kind == "travel":
        return replace(state, scene=action.key, turn=state.turn + 1)
    if action.kind == "wait":
        return replace(state, turn=state.turn + 1)
    if action.kind == "transit":
        if world.dynamics is None or state.world_state is None:
            raise DirectorError("transit requires an approved dynamic world")
        passage = next((p for p in world.dynamics.passages
                        if p.key == action.key
                        and (p.source == state.scene
                             or p.bidirectional and p.destination == state.scene)), None)
        if passage is None:
            raise DirectorError("unrecognized or unlicensed transport route")
        destination = (passage.destination if state.scene == passage.source
                       else passage.source)
        inventory = set(state.acquired)
        if passage.consume_item is not None:
            if passage.consume_item not in inventory:
                raise DirectorError("transit fare not in actual inventory")
            inventory.remove(passage.consume_item)
        effect = apply_changes(
            state.world_state, passage.reputation_change,
            add_flags=(passage.grant_world_flag,)
            if passage.grant_world_flag is not None else (),
            passage=passage.key,
        )
        return replace(
            state, scene=destination, turn=state.turn + passage.cost_turns,
            acquired=tuple(sorted(inventory)), world_state=effect,
        )
    affordance = next(a for a in here.affordances if a.key == action.key)
    records = {(q, st, obj): n for q, st, obj, n in state.records}
    inventory = set(state.acquired)
    completed = set(state.complete)
    results = list(state.results)
    flags = set(state.narrative_flags)
    updated = dict(progress)
    for quest in world.quests:
        index = progress[quest.key]
        if index >= len(quest.stages) or not set(quest.requires_quests).issubset(completed):
            continue
        stage = quest.stages[index]
        if state.scene not in stage.scene_ids:
            continue
        signature = affordance.kind + ":" + affordance.target
        relevant = any(signature == p.kind + ":" + p.target for solution in stage.solutions
                       for p in solution.required) or any(
                           signature == p.kind + ":" + p.target for p in stage.optional
                       )
        if not relevant:
            continue
        key = (quest.key, stage.key, signature)
        records[key] = min(100, records.get(key, 0) + 1)
        # Only accept completion after a full set of actual, scene-validated
        # events. OR between approaches; AND within each parameter set.
        matching = [solution for solution in stage.solutions if all(
            records.get((quest.key, stage.key, p.kind + ":" + p.target), 0) >= p.count
            for p in solution.required
        )]
        if matching:
            solution = max(matching, key=lambda s: (s.creativity, s.key))
            elapsed = (state.turn + affordance.effort)
            # A dedicated stage start turn is encoded by the first recorded
            # event. The time measurement is per stage, not across other arcs.
            first = next(
                (r.turns for r in results[::-1] if r.quest == quest.key), 0
            )
            stage_effort = max(1, elapsed - first)
            speed_bonus = max(0, stage.time_target - stage_effort) * 3
            variety = len({item[2].split(":", 1)[0] for item in records
                           if item[0] == quest.key and item[1] == stage.key})
            creativity_bonus = solution.creativity * 2 + max(0, variety - 1) * 8
            optional_bonus = 15 * sum(
                records.get((quest.key, stage.key, p.kind + ":" + p.target), 0) >= p.count
                for p in stage.optional
            )
            ending = f"{quest.key}_{solution.outcome_flag}"
            lore = f"{quest.narrative_cause} {stage.lore} {quest.consequences} Choice: {solution.key}."
            results.append(DirectorResult(
                quest.key, stage.key, solution.key, stage_effort, speed_bonus,
                creativity_bonus, optional_bonus,
                100 + speed_bonus + creativity_bonus + optional_bonus,
                ending, lore,
            ))
            flags.add(solution.outcome_flag)
            updated[quest.key] = index + 1
            if updated[quest.key] == len(quest.stages):
                completed.add(quest.key)
    if affordance.consumes:
        inventory.remove(affordance.consumes)
    if affordance.produces:
        inventory.add(affordance.produces)
    # At most one action per scene per step; all satisfied quests may progress.
    dynamics_state = state.world_state
    if world.dynamics is not None:
        if dynamics_state is None:
            raise DirectorError("world reputation snapshot missing")
        effects, gained, fired = effects_for_use(
            world.dynamics, dynamics_state,
            scene=here.key, affordance=affordance.key,
        )
        dynamics_state = apply_changes(
            dynamics_state, effects, add_flags=gained, fired=fired,
        )
        effects, gained, fired = effects_for_results(
            world.dynamics, dynamics_state,
            results=tuple(results[len(state.results):]),
        )
        dynamics_state = apply_changes(
            dynamics_state, effects, add_flags=gained, fired=fired,
        )
    return replace(
        state, turn=state.turn + affordance.effort,
        stage_index=tuple((q.key, updated[q.key]) for q in world.quests),
        complete=tuple(sorted(completed)),
        records=tuple(sorted((q, st, signature, count)
                             for (q, st, signature), count in records.items())),
        acquired=tuple(sorted(inventory)), results=tuple(results),
        narrative_flags=tuple(sorted(flags)), world_state=dynamics_state,
    )


@dataclass(frozen=True, slots=True)
class DirectorReplay:
    world_digest: str
    initial_digest: str
    actions: tuple[DirectorAction, ...]
    state_digests: tuple[str, ...]
    final: DirectorState

    @property
    def digest(self):
        return canonical_digest(self.payload())

    def payload(self):
        return dict(schema="skeleton.game_builder.director_replay.v1",
                    world_digest=self.world_digest, initial_digest=self.initial_digest,
                    actions=[a.payload() for a in self.actions],
                    state_digests=list(self.state_digests), final=self.final.payload())


def director_play(world: DirectorWorld, actions: Sequence[DirectorAction]) -> DirectorReplay:
    if not isinstance(actions, (list, tuple)) or len(actions) > MAX_EVENTS:
        raise DirectorError("oversized original quest action trace")
    state = director_initial(world)
    genesis = state.digest
    digests = []
    for action in actions:
        state = director_step(world, state, action)
        digests.append(state.digest)
    return DirectorReplay(world.digest, genesis, tuple(actions), tuple(digests), state)


def director_verify(world: DirectorWorld, replay: DirectorReplay) -> None:
    if not isinstance(replay, DirectorReplay) or replay.world_digest != world.digest:
        raise DirectorError("foreign or invalid quest replay")
    expected = director_play(world, replay.actions)
    if (expected.initial_digest != replay.initial_digest
            or expected.state_digests != replay.state_digests
            or expected.final != replay.final):
        raise DirectorError("quest replay, score, causality or progress tampered")


def quest_methods(world: DirectorWorld, quest_key: str, stage_key: str) -> tuple[tuple[DirectorAction, ...], ...]:
    """Find real legal action witnesses for alternative stage solutions.

    Routes are BFS shortest paths in the authored scene graph. This solver
    proves each objective can be performed; it is not a rigid quest checklist
    nor a claim of exhaustive optimal policy in the full nonlinear game.
    """
    q = next((q for q in world.quests if q.key == quest_key), None)
    if q is None:
        raise DirectorError("unknown original quest")
    stage = next((s for s in q.stages if s.key == stage_key), None)
    if stage is None:
        raise DirectorError("unknown quest stage")
    methods = []
    for solution in stage.solutions:
        tasks = []
        for p in solution.required:
            site = next((
                s for s in world.scenes if s.key in stage.scene_ids
                and any(a.kind == p.kind and a.target == p.target for a in s.affordances)
            ), None)
            if site is None:
                raise DirectorError("unreachable victory evidence")
            affordance = next(a for a in site.affordances
                              if a.kind == p.kind and a.target == p.target)
            tasks.extend(DirectorAction("use", affordance.key, site.key)
                         for _ in range(p.count))
        methods.append(tuple(tasks))
    return tuple(methods)


__all__ = [
    "DirectorError", "Cue", "Cutscene", "Affordance", "Scene", "Parameter",
    "Solution", "QuestStage", "QuestArc", "NarrativeBible", "DirectorWorld",
    "DirectorAction", "DirectorState", "DirectorResult", "DirectorReplay",
    "director_initial", "available_director_actions", "director_step",
    "director_play", "director_verify", "quest_methods", "ARCHETYPES",
    "ACTION_TYPES", "CUE_TYPES", "WorldDynamics", "WorldState",
]
