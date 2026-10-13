"""Source-grounded chapter chat turns for Jeeves and Studio.

This is deterministic conversation coordination, not a fake LLM call.
Each chat turn receives an exact story work order and a bounded verified
chapter context; a tampered, cross-project or stale transcript fails closed.
No chat message can approve unreviewed game sources.
"""
from __future__ import annotations
from .story_canon_fabric import StoryCanonError, digest, require, shape, text
from .story_workspace import load_story_workspace, load_continuity_contract
from .jeeves_production_director import work_order
from .story_chapter_context import chapter_context

SESSION = "skeleton.game_builder.jeeves_chapter_chat_session.v1"
MAX_TURNS = 64


def chat_turn(workspace, project, message, *, session=None,
              cast=None, region=None, act=None, scene=None):
    text(message,"human original-game chat instruction",10000)
    require(message.strip(), "empty Jeeves creative instruction")
    bible, scenes, index = load_story_workspace(workspace, project)
    contract = load_continuity_contract(workspace, project) if bible else None
    context_receipt = index["digest"] if index else None
    old_turns = []
    predecessor = None
    if session is not None:
        shape(session, ("schema","project","story_index_digest",
                        "contract_digest","turns","digest"),
              "chapter conversation source receipt")
        require(session["schema"] == SESSION and
                session["project"] == project and
                session["story_index_digest"] == context_receipt and
                session["contract_digest"] ==
                    (contract["digest"] if contract else None),
                "different project or changed canonical story requires fresh chat context")
        require(type(session["turns"]) is list and
                len(session["turns"]) < MAX_TURNS,
                "finite conversation receipt budget exceeded")
        require(session["digest"] == digest({k:v for k,v in session.items()
                                            if k!="digest"}),
                "chat history was altered or forged")
        old_turns = session["turns"]
        previous_turn = None
        for i,row in enumerate(old_turns):
            shape(row, ("sequence","prompt","work_order_digest",
                        "previous_turn_digest","digest"),
                  "human/Jeeves exchange receipt")
            text(row["prompt"],"conversation prompt",10000)
            require(row["sequence"]==i+1 and
                    row["previous_turn_digest"] == previous_turn and
                    row["digest"] == digest({k:v for k,v in row.items()
                                            if k!="digest"}),
                    "altered or skipped chat turn")
            previous_turn=row["digest"]
        predecessor=previous_turn
    order=work_order(workspace,project,message,cast=cast,region=region,
                     act=act,scene=scene)
    current_chapter = (chapter_context(bible,contract,scenes)
                       if bible is not None and contract is not None else None)
    body={
        "sequence":len(old_turns)+1,
        "prompt":message,
        "work_order_digest":order["digest"],
        "previous_turn_digest":predecessor,
    }
    new_turn={**body,"digest":digest(body)}
    state={
        "schema":SESSION,"project":project,
        "story_index_digest":context_receipt,
        "contract_digest":contract["digest"] if contract else None,
        "turns":[*old_turns,new_turn],
    }
    state={**state,"digest":digest(state)}
    result={
        "schema":"skeleton.game_builder.jeeves_chapter_chat_turn.v1",
        "project":project,
        "session":state,"work_order":order,
        "active_chapter":current_chapter,
        "story_index_digest":context_receipt,
        "source_mutated":False,
        "model_inference_performed":False,
        "provider_connected":False,
        "scene_autonomously_published":False,
        "human_commit_approval_required":True,
        "verified_chapter_context_available":current_chapter is not None,
        "claimed_perfect_cinematic_quality":False,
    }
    return {**result,"digest":digest(result)}
