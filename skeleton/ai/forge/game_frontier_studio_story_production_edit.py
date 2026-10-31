"""Twenty-five native quest-graph and in-game dialogue/cutscene/event composers.

Rewrites real canonical StudioQuest / StudioEvent source. Native quest parser
validates reachable stage IDs and the normal Studio compiler exports results.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from .game_frontier_studio import (
    StudioError, StudioProject, StudioQuest, StudioQuestStage, StudioEvent,
)
from .game_frontier_studio_map_edit import _name, _integer
from .game_frontier_studio_narrative_edit import _no_cycle

STORY_PRODUCTION_ACTIONS = (
    "quest_add_prologue", "quest_add_epilogue", "quest_extend_terminal",
    "quest_fork_terminal", "quest_bridge_endings", "quest_detour_leaf",
    "quest_stage_reparent", "quest_swap_branches", "quest_order_choices",
    "quest_backfill_objectives", "quest_template_sequence",
    "quest_template_binary_tree", "quest_stage_cleanup", "quest_mirror_branch",
    "quest_convert_to_linear", "event_stage_dialogue", "event_stage_flag",
    "event_stage_cutscene", "event_stage_music", "event_stage_item",
    "event_stage_camera", "event_stage_portal", "event_trigger_promote",
    "event_flag_gate", "event_mass_duplicate",
)


def _text(args, key, limit=512):
    value=args.get(key)
    if type(value) is not str or not 1<=len(value.strip())<=limit:
        raise StudioError("source narrative requires bounded nonempty text: "+key)
    return value


def _quest(project,args):
    ident=_name(args,"quest_id")
    for i,q in enumerate(project.native_quests):
        if q.quest_id==ident:
            return i,q
    raise StudioError("selected native quest is not present")


def _event(project,args):
    ident=_name(args,"event_id")
    for i,e in enumerate(project.events):
        if e.event_id==ident:
            return i,e
    raise StudioError("authored event does not exist")


def _stage(quest,name):
    for i,s in enumerate(quest.stages):
        if s.stage_id==name:
            return i,s
    raise StudioError("stage ID not in canonical quest graph")


def _replace(items,index,value):
    return items[:index]+(value,)+items[index+1:]


def _append_safe(stages,more):
    if len(stages)+len(more)>4096:
        raise StudioError("longform quest stage budget exceeded")
    old={s.stage_id for s in stages}
    ids=[s.stage_id for s in more]
    if len(ids)!=len(set(ids)) or any(sid in old for sid in ids):
        raise StudioError("generated quest identities overlap authoritative stages")
    return stages+more


def _save_quest(project,index,quest,stages):
    updated=replace(quest,stages=tuple(stages))
    _no_cycle(updated)
    return replace(project,native_quests=_replace(project.native_quests,index,updated))


def edit_story_production(project: StudioProject, operation: str,
                          args: Mapping[str, Any]) -> StudioProject:
    if not isinstance(project,StudioProject) or operation not in STORY_PRODUCTION_ACTIONS or not isinstance(args,Mapping):
        raise StudioError("unknown native story composition operation")
    if operation.startswith("quest_"):
        index,quest=_quest(project,args)
        stages=list(quest.stages)
        if operation=="quest_add_prologue":
            ident=_name(args,"new_stage_id")
            stages=_append_safe(stages,[StudioQuestStage(ident,_text(args,"objective"),(quest.first_stage_id,))])
            quest=replace(quest,first_stage_id=ident)
        elif operation in ("quest_add_epilogue","quest_bridge_endings"):
            ident=_name(args,"new_stage_id")
            terminal=[i for i,s in enumerate(stages) if not s.next_stage_ids]
            if operation=="quest_bridge_endings" and len(terminal)<2:
                raise StudioError("merging story endings requires multiple authored branches")
            for i in terminal:
                stages[i]=replace(stages[i],next_stage_ids=(ident,))
            stages=_append_safe(stages,[StudioQuestStage(ident,_text(args,"objective"))])
        elif operation=="quest_extend_terminal":
            sid=_name(args,"stage_id")
            i,s=_stage(quest,sid)
            if s.next_stage_ids:
                raise StudioError("extension requires authored terminal stage")
            ident=_name(args,"new_stage_id")
            stages[i]=replace(s,next_stage_ids=(ident,))
            stages=_append_safe(stages,[StudioQuestStage(ident,_text(args,"objective"))])
        elif operation=="quest_fork_terminal":
            sid=_name(args,"stage_id")
            i,s=_stage(quest,sid)
            if s.next_stage_ids:
                raise StudioError("fork requires terminal node")
            prefix=_name(args,"prefix")
            objectives=args.get("objectives")
            if type(objectives) is not list or not 2<=len(objectives)<=16:
                raise StudioError("player-choice fork must contain 2..16 authored choices")
            new=[StudioQuestStage(f"{prefix}_{j:02d}",o)
                 for j,o in enumerate(objectives)]
            stages[i]=replace(s,next_stage_ids=tuple(n.stage_id for n in new))
            stages=_append_safe(stages,new)
        elif operation=="quest_detour_leaf":
            origin=_name(args,"stage_id")
            i,s=_stage(quest,origin)
            if len(s.next_stage_ids)>=32:
                raise StudioError("too many authored detours")
            ident=_name(args,"new_stage_id")
            stages[i]=replace(s,next_stage_ids=s.next_stage_ids+(ident,))
            stages=_append_safe(stages,[StudioQuestStage(ident,_text(args,"objective"))])
        elif operation=="quest_stage_reparent":
            stage=_name(args,"stage_id")
            parent=_name(args,"new_parent_id")
            _stage(quest,stage)
            j,owner=_stage(quest,parent)
            if stage==quest.first_stage_id or stage==parent:
                raise StudioError("cannot detach authoritative quest root or self-parent")
            if stage in owner.next_stage_ids:
                raise StudioError("new parent already has requested stage")
            stages=[replace(s,next_stage_ids=tuple(x for x in s.next_stage_ids if x!=stage))
                    for s in stages]
            owner=stages[j]
            if len(owner.next_stage_ids)>=32:
                raise StudioError("quest graph fanout exhausted")
            stages[j]=replace(owner,next_stage_ids=owner.next_stage_ids+(stage,))
        elif operation=="quest_swap_branches":
            a,b=_name(args,"stage_a"),_name(args,"stage_b")
            ia,sa=_stage(quest,a)
            ib,sb=_stage(quest,b)
            if ia==ib:
                raise StudioError("branch swap needs distinct stages")
            stages[ia]=replace(sa,next_stage_ids=sb.next_stage_ids)
            stages[ib]=replace(sb,next_stage_ids=sa.next_stage_ids)
        elif operation=="quest_order_choices":
            sid=_name(args,"stage_id")
            i,s=_stage(quest,sid)
            order=args.get("choices")
            if (type(order) is not list or len(order)!=len(s.next_stage_ids)
                    or any(type(v) is not str for v in order)
                    or set(order)!=set(s.next_stage_ids)):
                raise StudioError("branch reorder must exactly match authored destinations")
            stages[i]=replace(s,next_stage_ids=tuple(order))
        elif operation=="quest_backfill_objectives":
            prefix=_text(args,"prefix",128)
            stages=[replace(s,objective=prefix+" "+s.objective)
                    for s in stages]
        elif operation in ("quest_template_sequence","quest_template_binary_tree"):
            sid=_name(args,"stage_id")
            i,s=_stage(quest,sid)
            if s.next_stage_ids:
                raise StudioError("quest macro requires terminal stage")
            prefix=_name(args,"prefix")
            generated=[]
            if operation=="quest_template_sequence":
                count=_integer(args,"count",1,64)
                next_id=None
                for k in reversed(range(count)):
                    node=f"{prefix}_{k:03d}"
                    generated.append(StudioQuestStage(node,f"Chapter {k+1}: "+_text(args,"objective",256),
                               (next_id,) if next_id else ()))
                    next_id=node
                generated.reverse()
                stages[i]=replace(s,next_stage_ids=(next_id,))
            else:
                depth=_integer(args,"depth",1,6)
                count=2**(depth+1)-2
                for k in range(count):
                    name=f"{prefix}_{k:03d}"
                    children=tuple(f"{prefix}_{t:03d}" for t in (2*k+1,2*k+2)
                                   if t<count)
                    generated.append(StudioQuestStage(name,
                                     f"Choice {k+1}: "+_text(args,"objective",256),children))
                stages[i]=replace(s,next_stage_ids=(generated[0].stage_id,))
            stages=_append_safe(stages,generated)
        elif operation=="quest_stage_cleanup":
            sid=_name(args,"stage_id")
            if sid==quest.first_stage_id:
                raise StudioError("cannot delete quest entry stage")
            i,s=_stage(quest,sid)
            if len(s.next_stage_ids)!=1:
                raise StudioError("cleanup can only compress one-exit stages")
            target=s.next_stage_ids[0]
            stages=[replace(current,next_stage_ids=tuple(
                target if x==sid else x for x in current.next_stage_ids))
                    for current in stages if current.stage_id!=sid]
        elif operation=="quest_mirror_branch":
            sid=_name(args,"stage_id")
            parent=_name(args,"parent_stage_id")
            _stage(quest,sid)
            p,owner=_stage(quest,parent)
            prefix=_name(args,"prefix")
            source={s.stage_id:s for s in stages}
            descendants=set()
            pending=[sid]
            while pending:
                node=pending.pop()
                if node in descendants:
                    continue
                descendants.add(node)
                pending.extend(source[node].next_stage_ids)
                if len(descendants)>128:
                    raise StudioError("copy of quest branch exceeds bounded stages")
            links={name:f"{prefix}_{name}" for name in sorted(descendants)}
            generated=[
                StudioQuestStage(links[sid],source[sid].objective,
                                tuple(links[next_id] for next_id in source[sid].next_stage_ids))
                for sid in sorted(descendants)
            ]
            if len(owner.next_stage_ids)>=32:
                raise StudioError("source node cannot host new branch")
            stages[p]=replace(owner,next_stage_ids=owner.next_stage_ids+(links[sid],))
            stages=_append_safe(stages,generated)
        elif operation=="quest_convert_to_linear":
            # Explicitly authored order; cannot silently pick one of many endings.
            order=args.get("stage_order")
            ids=[s.stage_id for s in stages]
            if (type(order) is not list or len(order)!=len(ids)
                    or len(set(order))!=len(order)
                    or set(order)!=set(ids) or order[0]!=quest.first_stage_id):
                raise StudioError("linearization requires complete ordered quest stage IDs")
            originals={s.stage_id:s for s in stages}
            stages=[replace(originals[sid],next_stage_ids=(order[k+1],)
                           if k+1<len(order) else ())
                    for k,sid in enumerate(order)]
        else:
            raise StudioError("not a real authored quest operation")
        return _save_quest(project,index,quest,stages)
    if operation in ("event_trigger_promote","event_flag_gate"):
        index,event=_event(project,args)
        if operation=="event_trigger_promote":
            trigger=_text(args,"trigger",32)
            event=replace(event,trigger=trigger)
        else:
            event=replace(event,condition_flag=_name(args,"flag"),
                          condition_value=args.get("expected",True))
        return replace(project,events=_replace(project.events,index,event))
    if operation=="event_mass_duplicate":
        names=args.get("source_event_ids")
        prefix=_name(args,"prefix")
        if (type(names) is not list or not 1<=len(names)<=128
                or any(type(v) is not str for v in names)
                or len(set(names))!=len(names)):
            raise StudioError("batch requires distinct exact source event IDs")
        existing={e.event_id:e for e in project.events}
        if any(name not in existing for name in names):
            raise StudioError("cannot clone unregistered event")
        generated=[replace(existing[n],event_id=prefix+"_"+n) for n in names]
        if any(len(e.event_id)>128 or e.event_id in existing for e in generated):
            raise StudioError("event clone output would overwrite authored event")
        return replace(project,events=project.events+tuple(generated))
    if operation.startswith("event_stage_"):
        key=_name(args,"event_id")
        if any(e.event_id==key for e in project.events):
            raise StudioError("new story event identity collides")
        target=_text(args,"target",128)
        value=_text(args,"value",128)
        kind={
            "event_stage_dialogue":"show_dialogue",
            "event_stage_flag":"set_flag",
            "event_stage_cutscene":"play_cutscene",
            "event_stage_music":"play_audio",
            "event_stage_item":"grant_item",
            "event_stage_camera":"change_camera",
            "event_stage_portal":"open_portal",
        }[operation]
        trigger=_text(args,"trigger",32) if "trigger" in args else "quest"
        event=StudioEvent(key,trigger,"",True,kind,target,value)
        return replace(project,events=project.events+(event,))
    raise StudioError("unknown native narrative action")
