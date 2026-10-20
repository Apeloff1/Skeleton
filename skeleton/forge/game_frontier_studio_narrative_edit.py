"""Fifteen concrete narrative composition and RPG event-authoring operations.

Stage edges, playable quest branches and per-actor interaction event records
are changed in the existing Forge Studio source rather than returning reports.
Every quest rewrite is rechecked by the canonical native quest graph compiler.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

from .game_frontier_studio import (
    StudioProject, StudioError, StudioQuest, StudioQuestStage, StudioEvent,
)
from .game_frontier_studio_map_edit import _name, _integer

STORY_ACTIONS = (
    "narrative_branch_pair", "narrative_branch_multi",
    "narrative_extend_chain", "narrative_insert_stage",
    "narrative_bypass_stage", "narrative_relabel_quest",
    "narrative_fork_quest", "narrative_merge_endings",
    "event_clone", "event_batch_retarget", "event_batch_retrigger",
    "event_bind_quest", "event_actor_dialogue_batch",
    "event_actor_audio_batch", "event_actor_loot_batch",
)


def _text(args: Mapping[str,Any], key: str, bound=512) -> str:
    value=args.get(key)
    if type(value) is not str or not 1<=len(value.strip())<=bound:
        raise StudioError("authored narrative text is missing or oversized: "+key)
    return value


def _quest(project, args):
    name=_name(args,"quest_id")
    for i,q in enumerate(project.native_quests):
        if q.quest_id==name:
            return i,q
    raise StudioError("selected authored quest does not exist")


def _event(project,args):
    name=_name(args,"event_id")
    for i,ev in enumerate(project.events):
        if ev.event_id==name:
            return i,ev
    raise StudioError("event source identity does not exist")


def _stage(quest, name):
    for i,s in enumerate(quest.stages):
        if s.stage_id==name:
            return i,s
    raise StudioError("quest stage does not exist")


def _replace(items: tuple, i, value):
    return items[:i]+(value,)+items[i+1:]


def _sid(prefix,i):
    if not 1<=len(prefix)<=80:
        raise StudioError("generated stage prefix must fit canonical identities")
    return f"{prefix}_{i:03d}"


def _no_cycle(quest: StudioQuest):
    edges={s.stage_id:s.next_stage_ids for s in quest.stages}
    state={}
    def visit(node):
        if state.get(node)==1:
            raise StudioError("cyclic narrative stage path is forbidden")
        if state.get(node)==2:
            return
        state[node]=1
        for nxt in edges[node]:
            if nxt not in edges:
                raise StudioError("narrative branch has missing destination")
            visit(nxt)
        state[node]=2
    for name in edges:
        visit(name)


def _write_quest(project,position,quest):
    _no_cycle(quest)
    return replace(project,native_quests=_replace(project.native_quests,position,quest))


def _indices(project,args):
    rows=args.get("indices")
    if (type(rows) is not list or not 1<=len(rows)<=64
            or any(type(i) is not int or not 0<=i<len(project.placements) for i in rows)
            or len(set(rows))!=len(rows)):
        raise StudioError("explicit unique actual actor indices required")
    return rows


def _event_ids(project,args):
    rows=args.get("event_ids")
    existing={e.event_id for e in project.events}
    if (type(rows) is not list or not 1<=len(rows)<=256 or
            len(set(rows))!=len(rows) or
            any(type(v) is not str or v not in existing for v in rows)):
        raise StudioError("event batch requires existing exact distinct event identities")
    return set(rows)


def edit_story(project: StudioProject, action: str,
               args: Mapping[str,Any]) -> StudioProject:
    if not isinstance(project,StudioProject) or action not in STORY_ACTIONS or not isinstance(args,Mapping):
        raise StudioError("unknown original game narrative composition action")
    if action.startswith("narrative_"):
        position,quest=_quest(project,args)
        stages=list(quest.stages)
        if action in ("narrative_branch_pair","narrative_branch_multi"):
            parent=_name(args,"from_stage_id")
            i,s=_stage(quest,parent)
            n=2 if action=="narrative_branch_pair" else _integer(args,"choices",2,8)
            prefix=_name(args,"stage_prefix")
            added=[_sid(prefix,k+1) for k in range(n)]
            if any(stage.stage_id in added for stage in stages) or len(s.next_stage_ids)+n>32:
                raise StudioError("branch choices conflict with authored quest stage identities")
            objectives=args.get("objectives")
            if (type(objectives) is not list or len(objectives)!=n
                    or any(type(v) is not str or not 1<=len(v.strip())<=512
                           for v in objectives)):
                raise StudioError("each narrative branch needs its own original objective")
            stages[i]=replace(s,next_stage_ids=s.next_stage_ids+tuple(added))
            stages.extend(StudioQuestStage(node,text) for node,text in zip(added,objectives))
        elif action=="narrative_extend_chain":
            from_id=_name(args,"from_stage_id")
            i,s=_stage(quest,from_id)
            prefix=_name(args,"stage_prefix")
            objectives=args.get("objectives")
            if (type(objectives) is not list or not 1<=len(objectives)<=64 or
                    any(type(v) is not str or not 1<=len(v.strip())<=512 for v in objectives)):
                raise StudioError("longform chain needs 1..64 authored narrative objectives")
            new=[_sid(prefix,j+1) for j in range(len(objectives))]
            if any(x.stage_id in new for x in stages) or len(s.next_stage_ids)>=32:
                raise StudioError("narrative chain contains duplicate or excess stage links")
            stages[i]=replace(s,next_stage_ids=s.next_stage_ids+(new[0],))
            stages.extend(StudioQuestStage(node,desc,
                          (new[j+1],) if j+1<len(new) else ())
                          for j,(node,desc) in enumerate(zip(new,objectives)))
        elif action=="narrative_insert_stage":
            before=_name(args,"from_stage_id")
            after=_name(args,"to_stage_id")
            new=_name(args,"new_stage_id")
            i,s=_stage(quest,before)
            _stage(quest,after)
            if after not in s.next_stage_ids or any(stage.stage_id==new for stage in stages):
                raise StudioError("can insert only into existing authored transition")
            stages[i]=replace(s,next_stage_ids=tuple(new if edge==after else edge
                                                      for edge in s.next_stage_ids))
            stages.insert(i+1,StudioQuestStage(new,_text(args,"objective"),(after,)))
        elif action=="narrative_bypass_stage":
            name=_name(args,"stage_id")
            if name==quest.first_stage_id:
                raise StudioError("cannot bypass authoritative quest entry")
            i,s=_stage(quest,name)
            if len(s.next_stage_ids)!=1:
                raise StudioError("bypass supports only linear one-exit stages")
            nxt=s.next_stage_ids[0]
            stages=[replace(stage,next_stage_ids=tuple(
                nxt if child==name else child for child in stage.next_stage_ids))
                    for stage in stages if stage.stage_id!=name]
        elif action=="narrative_relabel_quest":
            name=_name(args,"new_quest_id")
            if any(q.quest_id==name for q in project.native_quests):
                raise StudioError("new quest ID is already claimed")
            q=replace(quest,quest_id=name)
            updated=tuple(replace(e,value=name) if e.action=="start_quest"
                          and e.value==quest.quest_id else e for e in project.events)
            return replace(project,native_quests=_replace(project.native_quests,position,q),events=updated)
        elif action=="narrative_fork_quest":
            name=_name(args,"new_quest_id")
            if any(q.quest_id==name for q in project.native_quests):
                raise StudioError("original quest fork ID already exists")
            title=_text(args,"title",256)
            clone=replace(quest,quest_id=name,title=title)
            return replace(project,native_quests=project.native_quests+(clone,))
        elif action=="narrative_merge_endings":
            ident=_name(args,"epilogue_id")
            if any(s.stage_id==ident for s in stages):
                raise StudioError("quest already has this ending")
            terminals=[s for s in stages if not s.next_stage_ids]
            if len(terminals)<2:
                raise StudioError("branch merging requires at least two live endings")
            stages=[replace(s,next_stage_ids=(ident,))
                    if not s.next_stage_ids else s for s in stages]
            stages.append(StudioQuestStage(ident,_text(args,"objective")))
        q=replace(quest,stages=tuple(stages))
        return _write_quest(project,position,q)
    if action=="event_clone":
        _,event=_event(project,args)
        name=_name(args,"new_event_id")
        if any(e.event_id==name for e in project.events):
            raise StudioError("event clone identity is already occupied")
        target=args.get("target",event.target)
        if type(target) is not str or not 1<=len(target)<=128:
            raise StudioError("event clone target invalid")
        return replace(project,events=project.events+(replace(event,event_id=name,target=target),))
    if action in ("event_batch_retarget","event_batch_retrigger"):
        ids=_event_ids(project,args)
        if action=="event_batch_retarget":
            target=_text(args,"target",128)
            events=tuple(replace(e,target=target) if e.event_id in ids else e
                         for e in project.events)
        else:
            trigger=_text(args,"trigger",32)
            events=tuple(replace(e,trigger=trigger) if e.event_id in ids else e
                         for e in project.events)
        return replace(project,events=events)
    if action=="event_bind_quest":
        quest_id=_name(args,"quest_id")
        if quest_id not in {q.quest_id for q in project.native_quests}:
            raise StudioError("cannot start nonexistent quest")
        event_id=_name(args,"event_id")
        if event_id in {e.event_id for e in project.events}:
            raise StudioError("event trigger ID already used")
        actor=_name(args,"target")
        event=StudioEvent(event_id,"interact","",True,"start_quest",actor,quest_id)
        return replace(project,events=project.events+(event,))
    if action in ("event_actor_dialogue_batch","event_actor_audio_batch","event_actor_loot_batch"):
        ids=_indices(project,args)
        prefix=_name(args,"event_prefix")
        content=_text(args,"value",128)
        mode={
            "event_actor_dialogue_batch":"show_dialogue",
            "event_actor_audio_batch":"play_audio",
            "event_actor_loot_batch":"grant_item",
        }[action]
        new=[]
        existing={e.event_id for e in project.events}
        for i in ids:
            source=project.placements[i]
            name=f"{prefix}_{i:05d}"
            if len(name)>128 or name in existing:
                raise StudioError("event ID collision in actor batch")
            new.append(StudioEvent(
                name,"interact","",True,mode,
                f"{source.prefab_id}:{i}",content))
        return replace(project,events=project.events+tuple(new))
    raise StudioError("unknown narrative authoring operation")
