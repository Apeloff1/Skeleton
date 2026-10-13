"""Source-authenticated search and comparisons of real original game timelines.

No generated event summaries are allowed as evidence. The query index is
reconstructed from actual replayed player actions, physically moved NPCs,
event-ledger facts, witnesses and cryptographic *content hashes*. An imported
record is independently reconstructed and checked against all true sources.
"""
from __future__ import annotations

from .advanced_fast_chunk_snapshot import (
    prepare_verified_chunk_snapshot, MAX_BRANCHES,
)
from .advanced_chunked_world_timeline import (
    _hash as evidence_hash, ChunkTimelineError,
    continue_chunked_world, verify_chunked_continuation,
)

SCHEMA = "skeleton.game_builder.original_npc_provenance_index.v1"
KINDS = ("all", "action", "gameplay_event", "physical_move", "physical_event")
MAX_PAGE = 48
MAX_OFFSET = 4096
MAX_QUERY_TURN = 128


def _query_spec(query):
    if query is None:
        query = {}
    if type(query) is not dict or set(query) - {
        "kind", "actor_id", "from_turn", "to_turn", "offset", "limit"
    }:
        raise ChunkTimelineError("only six bounded original game history query controls supported")
    q = {
        "kind": "all", "actor_id": None,
        "from_turn": 0, "to_turn": 128,
        "offset": 0, "limit": 24,
        **query,
    }
    if q["kind"] not in KINDS or type(q["kind"]) is not str:
        raise ChunkTimelineError("unknown original physical source record kind")
    if q["actor_id"] is not None and (
        type(q["actor_id"]) is not str
        or not q["actor_id"].startswith("original_chunk_npc:")
        or len(q["actor_id"]) != len("original_chunk_npc:000")
        or not q["actor_id"][-3:].isascii()
        or not q["actor_id"][-3:].isdigit()
    ):
        raise ChunkTimelineError("actor filter requires an exact original citizen source ID")
    for key, high in (
        ("from_turn", MAX_QUERY_TURN), ("to_turn", MAX_QUERY_TURN),
        ("offset", MAX_OFFSET), ("limit", MAX_PAGE),
    ):
        low = 1 if key == "limit" else 0
        if type(q[key]) is not int or not low <= q[key] <= high:
            raise ChunkTimelineError("invalid bounded original historical index "+key)
    if q["from_turn"] > q["to_turn"]:
        raise ChunkTimelineError("inverted original event chronology")
    return q


def _metrics(world):
    s=world["state"]
    return {
        "tick": s["tick"],
        "player": s["player"],
        "people": len(s["actors"]),
        "physical_npc_moves": s["scheduler"]["physical_moves"],
        "detailed_actor_updates": s["scheduler"]["detailed_updates"],
        "deferred_actor_turns": s["scheduler"]["deferred_actor_turns"],
        "firsthand_physical_events": len(s["events"]),
        "direct_witnesses": sum(len(e["direct_witnesses"]) for e in s["events"]),
        "firsthand_dialogues": sum(
            x["source"] == "firsthand_physical_witness" for x in s["dialogues"]
        ),
        "paid_social_choices": len(s["choices"]),
        "quest_milestones": s["completed"],
        "remaining_supplies": s["inventory"]["supplies"],
        "remaining_stamina": s["inventory"]["stamina"],
        "retired": s["retired"],
        "finished": s["finished"],
    }


def _checked_variants(variants):
    if type(variants) not in (list,tuple) or not 1 <= len(variants) <= MAX_BRANCHES:
        raise ChunkTimelineError("one to twelve original game worlds required")
    names=set();normalized=[]
    for item in variants:
        if type(item) is not dict or set(item)!={"name","actions"}:
            raise ChunkTimelineError("history choice requires exact name and action list")
        name,actions=item["name"],item["actions"]
        if (type(name) is not str or not 1<=len(name)<=32
            or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-"
                   for c in name) or name in names):
            raise ChunkTimelineError("duplicate or unsafe original historical branch identity")
        if type(actions) not in (tuple,list) or len(actions)>128 or any(
            type(x) is not str or not 1<=len(x)<=32 for x in actions
        ):
            raise ChunkTimelineError("bounded original actual game commands required")
        names.add(name);normalized.append({"name":name,"actions":list(actions)})
    return normalized


def analyze_original_npc_histories(checkpoint, variants, *, cursor=None, query=None):
    """Compare actual divergent worlds with indexed source-record pagination."""
    variants=_checked_variants(variants)
    q=_query_spec(query)
    prepared=prepare_verified_chunk_snapshot(checkpoint,cursor=cursor)
    baseline=prepared.fork([])["result"]
    original_metrics=_metrics(baseline)
    observations=[]
    page=[];matched=0
    by_kind={kind:0 for kind in KINDS if kind!="all"}

    def emit(kind, branch, step, tick, payload, source_head, inherited):
        nonlocal matched
        if kind not in by_kind:
            raise ChunkTimelineError("unregistered source index record")
        by_kind[kind]+=1
        if q["kind"] not in ("all",kind) or not q["from_turn"]<=tick<=q["to_turn"]:
            return
        actor_id=q["actor_id"]
        if actor_id is not None:
            if kind != "physical_move" or payload["actor"] != actor_id:
                if kind != "physical_event" or actor_id not in payload["direct_witness_ids"]:
                    return
        if q["offset"]<=matched<q["offset"]+q["limit"]:
            page.append({
                "branch":branch,"kind":kind,"step":step,"tick":tick,
                "payload":payload,"authority_head":source_head,
                "inherited_source_prefix":inherited,
            })
        matched+=1

    for variant in variants:
        name=variant["name"]
        branch=prepared.fork(variant["actions"])
        game=branch["result"]
        state=game["state"]
        for row in game["trace"]:
            step=row["step"];tick=row["tick"];inherited=step<prepared.cursor
            head=row["digest"]
            emit("action",name,step,tick,
                 {"command":row["command"]},head,inherited)
            for number,term in enumerate(row["causal_events"]):
                emit("gameplay_event",name,step,tick,
                     {"index":number,"source_rule":term},head,inherited)
            for move in row["physical_moves"]:
                emit("physical_move",name,step,tick,{
                    "actor":move["actor"],"from":move["from"],"to":move["to"],
                    "from_chunk":move["from_chunk"],"to_chunk":move["to_chunk"],
                    "one_tile":move["one_tile"],
                },head,inherited)
        for fact in state["events"]:
            # The original action records its event using preincrement tick.
            # Frame step == event.tick, and executed frame tick == step+1.
            index=fact["tick"]
            if type(index) is not int or not 0<=index<len(game["trace"]):
                raise ChunkTimelineError("original witnessed fact lacks an exact action")
            row=game["trace"][index]
            emit("physical_event",name,index,row["tick"],{
                "source_event_id":fact["id"],"source_kind":fact["kind"],
                "site":fact["site"],"position":fact["position"],
                "direct_witness_ids":[
                    "original_chunk_npc:%03d"%i
                    for i in fact["direct_witnesses"]
                ],
            },row["digest"],index<prepared.cursor)
        current=_metrics(game)
        observations.append({
            "branch":name, "original_suffix":variant["actions"],
            "world_digest":game["digest"],
            "source_head":game["head_digest"],
            "metrics":current,
            "delta_from_original_cursor":{
                key:current[key]-original_metrics[key]
                for key in original_metrics
                if type(current[key]) is int
            },
            "real_earned_quests":[{
                "id":x["id"],"origin_event":x["event_id"],
                "site":x["site"],"ending":x["ending"],
                "status":x["status"],"followups":x["followups"],
                "actual_testimonies":list(x["testimonies"]),
            } for x in state["quests"]],
        })
    body={
        "schema":SCHEMA,"source_checkpoint":checkpoint,
        "source_cursor":prepared.cursor,
        "source_cursor_head":baseline["head_digest"],
        "query":q,"variants":variants,
        "baseline_metrics":original_metrics,
        "comparisons":observations,
        "matching_record_count":matched,
        "returned_record_count":len(page),
        "next_offset":q["offset"]+len(page) if matched>q["offset"]+len(page) else None,
        "indexed_causal_record_counts":by_kind,
        "records":page,
        "records_reconstructed_from_actual_game_trace":True,
        "source_world_files_mutated":False,
        "native_hardware_benchmark_certified":False,
        "model_weights_promoted":False,
    }
    body["digest"]=evidence_hash(body)
    return body


def verify_original_npc_histories(record):
    """Untrusted histories must be rerun and compared to real source games."""
    if type(record) is not dict or record.get("schema")!=SCHEMA:
        raise ChunkTimelineError("source-authenticated original NPC history index required")
    try:
        expected=analyze_original_npc_histories(
            record["source_checkpoint"],record["variants"],
            cursor=record["source_cursor"],query=record["query"])
    except (KeyError,TypeError,IndexError,ValueError) as exc:
        raise ChunkTimelineError("illegal or forged original world history query") from exc
    if expected != record:
        raise ChunkTimelineError("indexed original eyewitness, actor or state evidence changed")
    for variant,observed in zip(record["variants"],record["comparisons"]):
        full=continue_chunked_world(
            record["source_checkpoint"],variant["actions"],
            cursor=record["source_cursor"])
        if (not verify_chunked_continuation(full)
            or full["result_world_digest"]!=observed["world_digest"]
            or full["result"]["head_digest"]!=observed["source_head"]):
            raise ChunkTimelineError("actual from-genesis source trace did not match indexed branch")
    return True


__all__=[
    "SCHEMA","KINDS","MAX_PAGE",
    "analyze_original_npc_histories","verify_original_npc_histories",
]
