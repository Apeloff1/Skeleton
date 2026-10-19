"""Replay native Godot RPG observations into explicitly approved game-session state.

The authored GDD and Godot evidence remain the source of truth for sensory
conditions. This module *simulates* a playable quest state, boolean flags,
branch transitions and audiovisual cue queues. A local approval manifest
gates every mutating event page; its digest proves integrity, NOT an operator
identity. No Godot commands, global save mutations, or AI canon promotions.
"""
from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Mapping

from skeleton.forge.game_frontier_rpg_events import (
    RPGEventPage, evaluate_environment_events,
)
from .game_frontier_native_rpg_bridge import native_rpg_observations
from .game_frontier_receipt_journal import FrameReceiptJournal


class NativeQuestSessionError(ValueError):
    """Malformed source, illicit transition or unverified operator selection."""


_ID=re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_HEX=re.compile(r"^[0-9a-f]{64}$")
_PRESENTATION=frozenset({"show_dialogue", "play_cutscene", "play_music",
                          "spatial_audio", "change_camera", "inspect_instrument",
                          "trigger_impact_fx", "trigger_foliage_fx"})


def _sha(data: object) -> str:
    return sha256(json.dumps(data,sort_keys=True,separators=(",",":"),
                             allow_nan=False).encode("utf-8")).hexdigest()


def _identifier(value: object, label: str) -> str:
    if type(value) is not str or _ID.fullmatch(value) is None:
        raise NativeQuestSessionError(f"invalid {label}")
    return value


def parse_native_quest_graph(source: object) -> dict:
    """Validate all declarative quest edges, origins, reachability and IDs."""
    if (type(source) is not dict or source.get("schema") !=
        "skeleton.game.native_quest_graph.v1" or
        type(source.get("quests")) is not list or len(source["quests"])>128):
        raise NativeQuestSessionError("bounded authored quest graph required")
    if "receipt_digest" in source:
        copied={k:v for k,v in source.items() if k!="receipt_digest"}
        if source["receipt_digest"]!=_sha(copied):
            raise NativeQuestSessionError("authored quest graph digest mismatch")
    seen=set()
    quests=[]
    for quest in source["quests"]:
        if (type(quest) is not dict or set(quest)!={"id","title","start","stages"}
            or type(quest["title"]) is not str or
            not 1<=len(quest["title"])<=256 or
            type(quest["stages"]) is not list or
            not 1<=len(quest["stages"])<=4096):
            raise NativeQuestSessionError("exact source quest schema required")
        qid=_identifier(quest["id"],"quest ID")
        start=_identifier(quest["start"],"quest start")
        if qid in seen:
            raise NativeQuestSessionError("duplicate quest ID")
        seen.add(qid)
        graph={}
        ordered=[]
        for stage in quest["stages"]:
            if (type(stage) is not dict or set(stage)!={"id","objective","next"}
                or type(stage["objective"]) is not str
                or not 1<=len(stage["objective"])<=512
                or type(stage["next"]) is not list or len(stage["next"])>32):
                raise NativeQuestSessionError("exact quest stage schema required")
            sid=_identifier(stage["id"],"stage ID")
            if sid in graph:
                raise NativeQuestSessionError("duplicate stage ID")
            edges=[_identifier(node,"stage edge") for node in stage["next"]]
            if len(edges)!=len(set(edges)) or sid in edges:
                raise NativeQuestSessionError("repeated or self-loop quest branch")
            graph[sid]=edges
            ordered.append({"id":sid,"objective":stage["objective"],"next":edges})
        if start not in graph or any(edge not in graph for edges in graph.values()
                                         for edge in edges):
            raise NativeQuestSessionError("unresolved authored quest transition")
        visited={start}
        pending=[start]
        while pending:
            for edge in graph[pending.pop()]:
                if edge not in visited:
                    visited.add(edge)
                    pending.append(edge)
        if len(visited)!=len(graph) or not any(not edges for edges in graph.values()):
            raise NativeQuestSessionError("quest stages unreachable or without ending")
        quests.append({"id":qid,"title":quest["title"],"start":start,
                       "stages":ordered})
    output={"schema":"skeleton.game.native_quest_graph.v1","quests":quests}
    output["receipt_digest"]=_sha(output)
    return output


def authored_page_digest(pages: tuple[RPGEventPage,...]) -> str:
    """Identical page fingerprint to the read-only RPG timeline verifier."""
    if (type(pages) is not tuple or len(pages)>4096 or
        any(not isinstance(p,RPGEventPage) for p in pages) or
        len({p.page_id for p in pages})!=len(pages)):
        raise NativeQuestSessionError("unique typed authored RPG pages required")
    return _sha([{
        "id":p.page_id,"priority":p.priority,
        "conditions":[c.__dict__ for c in p.conditions],
        "actions":[a.__dict__ for a in p.actions],
        "cooldown_ms":p.cooldown_ms,"repeat":p.repeat,"enabled":p.enabled,
        "required_flags":p.required_flags,
    } for p in pages])


def _approved_manifest(approval: object, *, journal: FrameReceiptJournal,
                       actor_id: str, page_hash: str,
                       quest_hash: str) -> dict[tuple[int,str],dict]:
    if (type(approval) is not dict or set(approval)!={
        "schema","session_id","actor_id","track","signed_gdd_digest",
        "authored_pages_digest","quest_graph_digest","initial_flags",
        "approvals","receipt_digest"
    } or approval["schema"]!="skeleton.game.native_quest_approvals.v1" or
        approval["actor_id"]!=actor_id or approval["track"]!=journal.track or
        approval["signed_gdd_digest"]!=journal.gdd.source_digest or
        approval["authored_pages_digest"]!=page_hash or
        approval["quest_graph_digest"]!=quest_hash or
        approval["receipt_digest"]!=_sha({k:v for k,v in approval.items()
                                         if k!="receipt_digest"})):
        raise NativeQuestSessionError("unbound or corrupted session approval manifest")
    _identifier(approval["session_id"],"local session ID")
    flags=approval["initial_flags"]
    if (type(flags) is not dict or len(flags)>4096 or any(
        _ID.fullmatch(k) is None or type(v) is not bool
        for k,v in flags.items())):
        raise NativeQuestSessionError("bounded initial boolean flags required")
    entries=approval["approvals"]
    if type(entries) is not list or len(entries)>100000:
        raise NativeQuestSessionError("bounded explicit approvals list required")
    indexed={}
    for item in entries:
        if (type(item) is not dict or set(item)!={
                "frame","page_id","event_evidence_digest","frame_receipt_digest"}
            or type(item["frame"]) is not int or
            not 0<=item["frame"]<=1000000 or
            type(item["event_evidence_digest"]) is not str or
            _HEX.fullmatch(item["event_evidence_digest"]) is None or
            type(item["frame_receipt_digest"]) is not str or
            _HEX.fullmatch(item["frame_receipt_digest"]) is None):
            raise NativeQuestSessionError("invalid per-event approval evidence")
        key=(item["frame"],_identifier(item["page_id"],"approved page ID"))
        if key in indexed:
            raise NativeQuestSessionError("duplicate event approval")
        indexed[key]=item
    return indexed


def _stage_snapshot(graph: dict) -> dict[str,dict]:
    return {q["id"]:{"start":q["start"],
                     "edges":{s["id"]:s["next"] for s in q["stages"]}}
            for q in graph["quests"]}


def _apply_page(actions: list[dict], *, actor_id: str,
                graph: dict, quests: dict, flags: dict,
                frame: int) -> tuple[dict,dict,list[dict]]:
    """Validate a complete event atomically before recording any action."""
    quests={key:dict(value) for key,value in quests.items()}
    flags=dict(flags)
    cues=[]
    for action in actions:
        kind=action["kind"]
        value=action["value"]
        target=action["target"]
        if kind in ("start_quest","advance_quest"):
            if target!=actor_id or type(value) is not str:
                raise NativeQuestSessionError("quest action must target selected actor")
            if kind=="start_quest":
                qid=_identifier(value,"started quest")
                if qid not in graph or qid in quests:
                    raise NativeQuestSessionError("quest absent or already started")
                stage=graph[qid]["start"]
            else:
                parts=value.split(":")
                if len(parts)!=2:
                    raise NativeQuestSessionError("advance requires quest_id:stage_id")
                qid=_identifier(parts[0],"quest to advance")
                stage=_identifier(parts[1],"chosen branch")
                if qid not in quests or quests[qid]["completed"]:
                    raise NativeQuestSessionError("quest not active")
                previous=quests[qid]["stage"]
                if stage not in graph[qid]["edges"][previous]:
                    raise NativeQuestSessionError("unauthorized quest branch")
            quests[qid]={"stage":stage,
                         "completed":not bool(graph[qid]["edges"][stage]),
                         "last_transition_frame":frame}
        elif kind=="set_flag":
            if target!=actor_id or type(value) is not str or "=" not in value:
                raise NativeQuestSessionError("flag action requires name=true|false")
            name,truth=value.split("=",1)
            _identifier(name,"flag name")
            if truth not in ("true","false"):
                raise NativeQuestSessionError("boolean flag action required")
            flags[name]=truth=="true"
        elif kind in ("craft_item","set_npc_emotion",
                       "take_damage","heal_health","consume_item","award_xp",
                       "unlock_skill","set_faction_reputation"):
            if target!=actor_id:
                raise NativeQuestSessionError("local game world action targets wrong actor")
            cues.append({"kind":kind,"target":target,"cue":value,
                         "state":"queued_for_explicit_engine_approval"})
        elif kind in _PRESENTATION:
            if target!=actor_id:
                raise NativeQuestSessionError("presentation target differs from actor")
            cues.append({"kind":kind,"target":target,"cue":value,
                         "state":"queued_not_dispatched"})
        else:
            raise NativeQuestSessionError("world-impacting action requires real engine gateway")
    return quests,flags,cues


def simulate_native_quest_session(
    journal: FrameReceiptJournal, pages: tuple[RPGEventPage,...],
    quest_graph: object, approval: object, *,
    actor_id: str, scene_candidate_digest: str,
    through_frame: int | None = None,
    start_frame: int = 0, limit: int = 256,
) -> dict:
    """Recompute Godot evidence and execute *only locally approved* quest moves.

    Start pagination never resets quest state, flags or page cooldowns. The
    entire native prefix is always authenticated by the existing journal.
    """
    if (not isinstance(journal,FrameReceiptJournal) or
        type(actor_id) is not str or not 1<=len(actor_id)<=128 or
        type(scene_candidate_digest) is not str or
        _HEX.fullmatch(scene_candidate_digest) is None or
        type(start_frame) is not int or start_frame<0 or
        type(limit) is not int or not 1<=limit<=4096 or
        through_frame is not None and (
            type(through_frame) is not int or through_frame<0)):
        raise NativeQuestSessionError("bounded source-bound game session required")
    graph=parse_native_quest_graph(quest_graph)
    page_hash=authored_page_digest(pages)
    approvals=_approved_manifest(approval,journal=journal,actor_id=actor_id,
                                 page_hash=page_hash,
                                 quest_hash=graph["receipt_digest"])
    stats=journal.stats()
    end=stats["head"] if through_frame is None else through_frame
    if end<start_frame or end>stats["head"] or end>1000000 or end-start_frame+1>limit:
        raise NativeQuestSessionError("game session frame range exceeds source or page limit")
    if journal.replay(through=end)["verified_frames"]!=end+1:
        raise NativeQuestSessionError("native journal prefix did not replay completely")
    for frame,_ in approvals:
        if frame>end:
            raise NativeQuestSessionError("approval points outside replayed game session")
    definitions=_stage_snapshot(graph)
    state={}
    flags=dict(approval["initial_flags"])
    last_fired={}
    completed=set()
    previous=None
    previous_receipt=None
    output=[]
    consumed=set()
    approved_count=0
    for index in range(end+1):
        native=journal.native_sample(index)
        if (native is None or native.get("scene_candidate_digest")!=scene_candidate_digest
            or native.get("signed_gdd_digest")!=journal.gdd.source_digest):
            raise NativeQuestSessionError("observed game scene or GDD identity mismatch")
        frame,chunk=journal.load(index)
        if frame.fps!=native.get("fps"):
            raise NativeQuestSessionError("source engine fixed-clock mismatch")
        observed=native_rpg_observations(native,actor_id=actor_id)
        now_ms=frame.time_ns//1_000_000
        decision=evaluate_environment_events(
            pages,current=observed,previous=previous,flags=flags,now_ms=now_ms,
            last_fired_ms=last_fired,completed_once=frozenset(completed))
        permitted=[]
        proposals=[]
        cues=[]
        for proposal in decision.accepted:
            last_fired[proposal.page_id]=now_ms
            completed.add(proposal.page_id)
            key=(index,proposal.page_id)
            selected=approvals.get(key)
            proposals.append({"page_id":proposal.page_id,
                              "event_evidence_digest":proposal.evidence_digest,
                              "operator_approved":selected is not None})
            if selected is not None:
                if (selected["event_evidence_digest"]!=proposal.evidence_digest
                    or selected["frame_receipt_digest"]!=frame.receipt_digest):
                    raise NativeQuestSessionError("approval references forged event or frame")
                actions=[action.__dict__ for action in proposal.actions]
                state,flags,page_cues=_apply_page(
                    actions,actor_id=actor_id,graph=definitions,
                    quests=state,flags=flags,frame=index)
                cues.extend(page_cues)
                permitted.append({"page_id":proposal.page_id,"actions":actions,
                                  "event_evidence_digest":proposal.evidence_digest})
                consumed.add(key)
                approved_count+=1
        result={
            "frame":index,"clock_ns":frame.time_ns,
            "source_frame_receipt_digest":frame.receipt_digest,
            "source_chunk_digest":chunk["receipt_digest"],
            "source_native_digest":_sha(native),
            "previous_session_receipt_digest":previous_receipt,
            "proposals":proposals,"approved_pages":permitted,
            "suppressed_page_ids":list(decision.suppressed),
            "missing_observations":list(decision.missing_signals),
            "quests":{key:state[key] for key in sorted(state)},
            "flags":{key:flags[key] for key in sorted(flags)},
            "presentation_cues":cues,
        }
        result["receipt_digest"]=_sha(result)
        previous_receipt=result["receipt_digest"]
        if index>=start_frame:
            output.append(result)
        previous=observed
    if consumed!=set(approvals):
        raise NativeQuestSessionError("approval lacks matching accepted source event")
    report={
        "schema":"skeleton.game.native_quest_session.v1",
        "session_id":approval["session_id"],
        "actor_id":actor_id,"track":journal.track,
        "signed_gdd_digest":journal.gdd.source_digest,
        "scene_candidate_digest":scene_candidate_digest,
        "authored_pages_digest":page_hash,
        "quest_graph_digest":graph["receipt_digest"],
        "approval_manifest_digest":approval["receipt_digest"],
        "source_prefix_verified_frames":end+1,
        "start_frame":start_frame,"through_frame":end,
        "approved_page_count":approved_count,
        "final_quests":{key:state[key] for key in sorted(state)},
        "final_flags":{key:flags[key] for key in sorted(flags)},
        "last_session_receipt_digest":previous_receipt,
        "entries":output,
        "authority":"operator_selected_local_gameplay_simulation_not_engine_world_save",
    }
    report["receipt_digest"]=_sha(report)
    return report


def verify_native_quest_session(
    journal: FrameReceiptJournal, pages: tuple[RPGEventPage,...],
    graph: object, approvals: object, recorded: dict, **kwargs
) -> bool:
    """Independent replay comparison rejects changed actions, flags and frames."""
    rebuilt=simulate_native_quest_session(journal,pages,graph,approvals,**kwargs)
    if type(recorded) is not dict or rebuilt!=recorded:
        raise NativeQuestSessionError("game session chain differs from source replay")
    return True
