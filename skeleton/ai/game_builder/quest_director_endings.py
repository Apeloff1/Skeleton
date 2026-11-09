"""Causally earned story endings from actual original quest-play receipts.

The canonical world goal never changes merely because a player chooses a
method. Available endings depend on solved arcs, evidence flags, optional
objectives and independently replayable choices, not a menu of labels.
"""
from __future__ import annotations

from dataclasses import dataclass

from .contracts import canonical_digest
from .quest_scene_engine import (
    DirectorError, DirectorReplay, DirectorWorld, director_verify,
)


_METHOD_AXIS = {
    "research": "discovery", "discover": "discovery", "inspect": "discovery",
    "solve": "discovery", "attune": "discovery", "train": "discovery",
    "negotiate": "stewardship", "heal": "stewardship", "protect": "stewardship",
    "escort_follow": "stewardship", "escort_leash": "stewardship",
    "repair": "stewardship", "talk": "stewardship",
    "sneak": "independence", "fight": "independence",
    "trade": "independence", "craft": "independence",
    "infuse": "independence", "build": "independence",
}


@dataclass(frozen=True, slots=True)
class StoryEnding:
    world_digest: str
    goal: str
    ending: str
    epilogue: str
    total_score: int
    effort_turns: int
    optional_victories: int
    main_quest_completed: bool
    qualifying_chapters: int
    supported_alternatives: tuple[str, ...]
    continuity_facts: tuple[str, ...]
    actions_digest: str

    @property
    def digest(self) -> str:
        return canonical_digest(self.payload())

    def payload(self):
        return {
            "schema": "skeleton.game_builder.earned_story_ending.v1",
            "world_digest": self.world_digest,
            "invariant_original_goal": self.goal,
            "earned_ending": self.ending,
            "epilogue": self.epilogue,
            "total_score": self.total_score,
            "effort_turns": self.effort_turns,
            "optional_victories": self.optional_victories,
            "main_quest_completed": self.main_quest_completed,
            "qualifying_chapters": self.qualifying_chapters,
            "supported_alternatives": list(self.supported_alternatives),
            "continuity_facts": list(self.continuity_facts),
            "actions_digest": self.actions_digest,
            "externally_generated_lore": False,
            "human_story_quality_verified": False,
        }


def evaluate_story_ending(
    world: DirectorWorld, replay: DirectorReplay, *,
    desired: str | None = None, authorized: bool,
) -> StoryEnding:
    if not authorized:
        raise PermissionError("narrative ending evaluation needs operator authority")
    if not isinstance(world, DirectorWorld) or not isinstance(replay, DirectorReplay):
        raise DirectorError("typed authored game with real quest replay required")
    director_verify(world, replay)
    final = replay.final
    main = [q for q in world.quests if q.scope == "main"]
    if not main or any(q.key not in final.complete for q in main):
        raise DirectorError("the invariant main story cannot end before its quests finish")
    flags = {r.approach: r for r in final.results}
    if not final.results or final.turn <= 0:
        raise DirectorError("no performed original player choices support an ending")
    axes = {"stewardship": 0, "discovery": 0, "independence": 0}
    for result in final.results:
        quest = next(q for q in world.quests if q.key == result.quest)
        chapter = next(s for s in quest.stages if s.key == result.stage)
        solution = next(s for s in chapter.solutions if s.key == result.approach)
        method_kinds = {p.kind for p in solution.required}
        for kind in method_kinds:
            axis = _METHOD_AXIS.get(kind, quest.ending_axis)
            if axis in axes:
                axes[axis] += 1
    earned = tuple(sorted(axis for axis, value in axes.items() if value > 0))
    if not earned:
        raise DirectorError("player did not produce an identifiable earned world outcome")
    if desired is not None and desired not in earned:
        raise DirectorError("requested ending is inconsistent with player's methods")
    chosen = desired if desired is not None else max(
        earned, key=lambda axis: (axes[axis], axis)
    )
    index = ("stewardship", "discovery", "independence").index(chosen)
    optional = sum(r.optional_bonus // 15 for r in final.results)
    outcome = world.bible.ending_outcomes[index]
    quality = ("with extraordinary care" if optional >= 3 else
               "with additional discoveries" if optional else
               "at a meaningful personal cost")
    epilogue = (
        world.bible.opening + " The original goal remained: " +
        world.bible.invariant_goal + " " + outcome + " " +
        "The player achieved this " + quality + ", through " +
        str(len(final.results)) + " completed original stages and " +
        str(final.turn) + " turns."
    )
    return StoryEnding(
        world.digest, world.bible.invariant_goal, chosen,
        epilogue, sum(r.score for r in final.results), final.turn,
        optional, True, len(final.results), earned,
        world.bible.canonical_facts,
        canonical_digest([a.payload() for a in replay.actions]),
    )


__all__ = ["StoryEnding", "evaluate_story_ending"]
