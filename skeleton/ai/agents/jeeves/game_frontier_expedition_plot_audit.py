"""Executable plot coverage for original interactive games, not script proofreading.

Visits all authored branch origins, selects both decisive opening choices, and
actually wins the physical game with a canonical production session. Records
the earned ending, quest progression and any unreachable authored branch.
Proof requires independently re-executing the entire event/action journal.
"""
from __future__ import annotations
from typing import Mapping
from .game_frontier_expedition import (
    ExpeditionWorld,Traveler,ExpeditionError,find_route,_digest,
)
from .game_frontier_expedition_narrative import StoryBook
from .game_frontier_expedition_quests import QuestBook
from .game_frontier_expedition_session import (
    ProductionInput,ProductionSession,verify_production_session,
)


def _travel_to(session:ProductionSession,where:str)->None:
    current=session.game.position
    if current==where:
        return
    path=find_route(session.game.world,session.game.traveler,where,start=current)
    for edge in path.edge_ids:
        session.submit(ProductionInput("gameplay","travel",edge))
    if session.game.position!=where:
        raise ExpeditionError("story progression cannot invent a physical waypoint")


def prove_original_story_branches(
    world:ExpeditionWorld,player:Traveler,story:StoryBook,quests:QuestBook,
    *, max_branches:int=16,
)->dict:
    if type(max_branches) is not int or not 1<=max_branches<=16:
        raise ExpeditionError("story branch exploration must be finite")
    baseline=ProductionSession(world,player,story,quests)
    if len(story.scenes)<3:
        raise ExpeditionError("plot verification requires a real multi-act source")
    opening=story.scenes[0]
    branches=opening.choices
    if not 2<=len(branches)<=max_branches:
        raise ExpeditionError("story's available divergent choices exceed budget")
    proofs=[]
    for choice in branches:
        session=ProductionSession(world,player,story,quests)
        if opening.waypoint!=session.game.position:
            raise ExpeditionError("opening story is disconnected from playable spawn")
        session.submit(ProductionInput("dialogue",scene_id=opening.scene_id,
                                       choice_id=choice.choice_id))
        for scene in story.scenes[1:]:
            _travel_to(session,scene.waypoint)
            offered={s.scene_id:s for s in session.story.offered(session.game)}
            if scene.scene_id not in offered:
                raise ExpeditionError(
                    "authored scene cannot be reached through this branch: "+scene.scene_id
                )
            # Explicit deterministic authored choice, not a fabricated quest flag.
            pick=scene.choices[0]
            session.submit(ProductionInput("dialogue",scene_id=scene.scene_id,
                                           choice_id=pick.choice_id))
        if not session.game.won:
            _travel_to(session,world.destinations[0])
        if not session.game.won:
            raise ExpeditionError("story arc does not end at a playable victory")
        terminal=session.ending()
        saved=session.snapshot()
        replay=verify_production_session(world,player,story,quests,saved)
        if not replay["source_replay_verified"] or replay["session_head"]!=session.head:
            raise ExpeditionError("story opponent could not re-execute canonical branch")
        proof={
            "opening_choice":choice.choice_id,
            "ending_id":terminal["ending_id"],
            "game_action_count":len(session.game.actions),
            "dialogue_choices":len(session.story.moments),
            "quest_events":len(session.quests.events),
            "physical_victory":True,
            "ending_receipt":terminal["receipt_digest"],
            "gameplay_receipt":session.game.snapshot()["receipt_head"],
            "session_receipt":session.head,
            "snapshot_digest":saved["snapshot_digest"],
            "source_replayed":True,
        }
        proof["receipt_digest"]=_digest(proof)
        proofs.append(proof)
    unique_ends={x["ending_id"] for x in proofs}
    if len(unique_ends)<2:
        raise ExpeditionError("authored decisions did not cause genuinely different endings")
    report={
        "schema":"skeleton.game.branching_story_playthrough_v1",
        "world_digest":world.digest,"story_digest":story.digest,
        "quest_digest":quests.digest,
        "opening_branches_executed":len(proofs),
        "distinct_endings_reached":len(unique_ends),
        "playthroughs":proofs,
        "all_branches_source_replayed":True,
        "native_engine_executed":False,
        "external_creative_signoff":False,
    }
    report["receipt_digest"]=_digest(report)
    return report
