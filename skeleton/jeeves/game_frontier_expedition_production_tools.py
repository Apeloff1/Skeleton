"""Jeeves' five governed, durable story+game+quest production operations.

Each action is a real source event loaded from and committed to SQLite under
the same host authorization used by existing Studio commands. Neither the
agent nor the command text may choose a new filesystem or fabricate ownership.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, Callable
import re

from .game_frontier_expedition import ExpeditionError,ExpeditionWorld,Traveler
from .game_frontier_expedition_narrative import StoryBook
from .game_frontier_expedition_quests import QuestBook
from .game_frontier_expedition_session import ProductionSession,ProductionInput
from .game_frontier_expedition_production_store import ProductionSessionStore
from .game_studio_tools import StudioCommand

READ_OPERATIONS=("expedition.production.inspect","expedition.production.ending")
WRITE_OPERATIONS=("expedition.production.start","expedition.production.act",
                  "expedition.production.choose")
_RUN=re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def production_studio_handlers(
    projects:Mapping[str,tuple[ExpeditionWorld,Traveler,StoryBook,QuestBook]],
    *, store:ProductionSessionStore,
)->dict[str,Callable[[StudioCommand,Any],dict]]:
    if not isinstance(projects,Mapping) or not projects or not isinstance(store,ProductionSessionStore):
        raise ExpeditionError("production commands require a host-owned project mapping and durable journal")
    pinned=dict(projects)
    for key,owner in pinned.items():
        if (type(key) is not str or not isinstance(owner,tuple) or
                len(owner)!=4 or
                not isinstance(owner[0],ExpeditionWorld) or
                not isinstance(owner[1],Traveler) or
                not isinstance(owner[2],StoryBook) or
                not isinstance(owner[3],QuestBook) or
                owner[0].project_id!=key or
                owner[2].world_digest!=owner[0].digest or
                owner[3].story_digest!=owner[2].digest):
            raise ExpeditionError("production project mapping must pin one real original source")
    def context(command:StudioCommand):
        if not isinstance(command,StudioCommand) or command.project_id not in pinned:
            raise ExpeditionError("production source is not owned or authorized")
        run=command.payload.get("run_id")
        if type(run) is not str or not _RUN.fullmatch(run):
            raise ExpeditionError("production run identity invalid")
        return pinned[command.project_id],command.project_id+":"+run

    def _read(command):
        (w,p,story,quest),run=context(command)
        loaded=store.load(run,w,p,story,quest)
        return (w,p,story,quest),run,loaded

    def inspect(command,_host):
        (w,p,story,quest),run,loaded=_read(command)
        if loaded is None:
            return {"schema":"skeleton.studio.production_inspect.v1",
                    "project":command.project_id,"run_id":run,
                    "exists":False,"source":w.digest}
        generation,session,receipt=loaded
        return {
            "schema":"skeleton.studio.production_inspect.v1",
            "project":command.project_id,"run_id":run,
            "exists":True,"source":w.digest,
            "generation":generation,"receipt":receipt,
            "game":session.game.state(),
            "story_choices":len(session.story.moments),
            "story_flags":sorted(session.story.flags),
            "quest_flags":sorted(session.quests.flags),
            "quest_progress":dict(session.quests.progress),
            "session_head":session.head,"native_engine_executed":False,
        }

    def start(command,_host):
        (w,p,story,quest),run,loaded=_read(command)
        if loaded is not None:
            raise ExpeditionError("production run already exists; resume instead")
        new=ProductionSession(w,p,story,quest)
        generation,receipt=store.save(run,new)
        return {"schema":"skeleton.studio.production_mutation.v1",
                "run_id":run,"generation":generation,"receipt":receipt,
                "session_head":new.head,"kind":"start",
                "source":w.digest}

    def _mutate(command,kind):
        (w,p,story,quest),run,loaded=_read(command)
        if loaded is None:
            raise ExpeditionError("production action needs an existing original run")
        generation,session,prior=loaded
        version=command.payload.get("expected_generation")
        if type(version) is not int or version!=generation:
            raise ExpeditionError("production action has a stale expected generation")
        if kind=="gameplay":
            entry=ProductionInput(
                "gameplay",action_kind=command.payload.get("kind",""),
                edge_id=command.payload.get("edge_id",""),
            )
        else:
            entry=ProductionInput(
                "dialogue",scene_id=command.payload.get("scene_id",""),
                choice_id=command.payload.get("choice_id",""),
            )
        result=session.submit(entry)
        next_version,next_receipt=store.save(
            run,session,expected_version=generation,
        )
        return {
            "schema":"skeleton.studio.production_mutation.v1",
            "run_id":run,"generation":next_version,
            "receipt":next_receipt,"prior_receipt":prior,
            "session_head":session.head,
            "event_receipt":result["receipt"],
            "kind":kind,"source":w.digest,
            "game":session.game.state(),
            "story_flags":sorted(session.story.flags),
            "quest_flags":sorted(session.quests.flags),
        }

    def act(command,_host):
        return _mutate(command,"gameplay")

    def choose(command,_host):
        return _mutate(command,"dialogue")

    def ending(command,_host):
        (w,p,story,quest),run,loaded=_read(command)
        if loaded is None:
            raise ExpeditionError("cannot resolve ending for nonexistent game")
        generation,session,receipt=loaded
        result=session.ending()
        return {
            **result,"schema":"skeleton.studio.production_ending.v1",
            "run_id":run,"generation":generation,
            "durable_receipt":receipt,
            "production_release_approved":False,
        }
    return {
        "expedition.production.inspect":inspect,
        "expedition.production.ending":ending,
        "expedition.production.start":start,
        "expedition.production.act":act,
        "expedition.production.choose":choose,
    }
