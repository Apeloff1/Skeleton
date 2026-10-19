"""Turn durable Godot physics into typed RPG event-page proposals.

No clock is invented: fixed-frame timestamps derive from the signed source
journal. Pages use the existing RPG Forge comparator, hysteresis, priority,
cooldown, repeat and action/channel conflict engine. The resulting event log
does NOT mutate quest canon, world state, inventories or scene executables.
"""
from __future__ import annotations

from hashlib import sha256
import json
import math
from typing import Mapping

from skeleton.forge.game_frontier_rpg_events import (
    EnvironmentalTrigger,RPGEventAction,RPGEventPage,
    evaluate_environment_events,RPGEventError,
)
from .game_frontier_receipt_journal import FrameReceiptJournal
from .game_frontier_native_dynamics import inspect_native_dynamics
from .game_frontier_native_zones import inspect_native_gameplay_zones


class NativeRPGBridgeError(ValueError):
    pass


def _digest(payload: object) -> str:
    return sha256(json.dumps(payload,sort_keys=True,separators=(",",":"),
                             allow_nan=False).encode()).hexdigest()


def parse_native_rpg_pages(payload: object) -> tuple[RPGEventPage,...]:
    """Strict bounded operator-authored event-page source, never executable."""
    if not isinstance(payload,dict) or payload.get("schema")!=(
        "skeleton.game.native_rpg_pages.v1"):
        raise NativeRPGBridgeError("source-typed game event pages JSON required")
    specs=payload.get("pages")
    if not isinstance(specs,list) or len(specs)>4096:
        raise NativeRPGBridgeError("bounded RPG event pages list required")
    output=[]
    try:
        for source in specs:
            if not isinstance(source,dict) or set(source)!={
                "id","priority","conditions","actions","cooldown_ms","repeat",
                "enabled","required_flags"}:
                raise NativeRPGBridgeError("exact authored RPG page schema required")
            if (not isinstance(source["conditions"],list) or
                not isinstance(source["actions"],list) or
                not isinstance(source["required_flags"],list)):
                raise NativeRPGBridgeError("typed RPG conditions/actions/flags required")
            output.append(RPGEventPage(
                page_id=source["id"],priority=source["priority"],
                conditions=tuple(EnvironmentalTrigger(**c)
                                 for c in source["conditions"]),
                actions=tuple(RPGEventAction(**a) for a in source["actions"]),
                required_flags=tuple((f["name"],f["value"])
                                     for f in source["required_flags"]),
                cooldown_ms=source["cooldown_ms"],
                enabled=source["enabled"],repeat=source["repeat"],
            ))
    except (TypeError,ValueError,KeyError,AttributeError) as exc:
        raise NativeRPGBridgeError("invalid declarative native RPG page") from exc
    if len({p.page_id for p in output})!=len(output):
        raise NativeRPGBridgeError("duplicate native game event page ID")
    return tuple(output)


def native_rpg_observations(sample: Mapping, *, actor_id: str) -> dict[str,float]:
    """Extract only physically reported game quantities, never guessed forces."""
    if not isinstance(sample,Mapping) or type(actor_id) is not str or not actor_id:
        raise NativeRPGBridgeError("typed observed native sample/actor required")
    actors=sample.get("actors")
    if not isinstance(actors,list) or len(actors)>256:
        raise NativeRPGBridgeError("native RPG actor source unavailable")
    candidates=[a for a in actors if isinstance(a,Mapping) and a.get("id")==actor_id]
    if len(candidates)!=1:
        raise NativeRPGBridgeError("native RPG actor must resolve uniquely")
    actor=candidates[0]
    coords=actor.get("world_xyz_m")
    velocity=actor.get("velocity_xyz_mps")
    if (not isinstance(coords,list) or not isinstance(velocity,list) or
        len(coords)!=3 or len(velocity)!=3 or
        any(type(x) not in (int,float) or not math.isfinite(x) or abs(x)>1e8
            for x in (*coords,*velocity))):
        raise NativeRPGBridgeError("finite source position and velocity required")
    contact=actor.get("contact_count")
    observations={
        "altitude_m":float(coords[2]),
        "fall_speed_mps":max(0.,-float(velocity[2])),
        "native_actor_speed_mps":math.dist([0.,0.,0.],velocity),
        "native_vertical_speed_mps":float(velocity[2]),
    }
    if type(contact) is int and 0<=contact<=64:
        observations["native_contact_count"]=float(contact)
    dynamics=inspect_native_dynamics(sample)
    if dynamics is not None:
        mass=next((d for d in dynamics["actors"] if d["id"]==actor_id),None)
        if mass is None:
            raise NativeRPGBridgeError("missing native physics body source")
        observations["character_mass_kg"]=mass["mass_kg"]
        observations["native_kinetic_energy_j"]=mass["kinetic_energy_j"]
    zone=inspect_native_gameplay_zones(sample)
    if zone is not None:
        events=[e for e in sample["native_zone_events"] if e["actor_id"]==actor_id]
        observations["native_gameplay_zone_entries"]=float(
            sum(e["transition"]=="enter" for e in events))
        observations["native_gameplay_zone_exits"]=float(
            sum(e["transition"]=="exit" for e in events))
        observations["native_gameplay_zone_occupants"]=float(
            sum(e["actor_id"]==actor_id for e in sample["native_zone_occupancy"]))
    return observations


def evaluate_native_rpg_timeline(
    journal: FrameReceiptJournal,
    pages: tuple[RPGEventPage,...], *,
    actor_id: str,
    start_frame: int = 0,
    limit: int = 256,
    flags: Mapping[str,bool] | None = None,
) -> dict:
    """Replay the complete observed prefix, with event state reconstructed.

    A page's cooldown and one-shot flag are derived from every prior tick,
    never reset at pagination boundaries. The result is a candidate-only
    read-only editor event log. It never authorizes RPG action execution.
    """
    if not isinstance(journal,FrameReceiptJournal) or (
        not isinstance(pages,tuple) or
        any(not isinstance(p,RPGEventPage) for p in pages) or len(pages)>4096 or
        len({p.page_id for p in pages})!=len(pages) or
        type(actor_id) is not str or not actor_id or len(actor_id)>128 or
        type(start_frame) is not int or start_frame<0 or start_frame>100000 or
        type(limit) is not int or not 1<=limit<=4096 or
        flags is not None and (not isinstance(flags,Mapping) or len(flags)>4096
                               or any(type(v) is not bool for v in flags.values()))):
        raise NativeRPGBridgeError("bounded authored native RPG evaluation request required")
    head=journal.stats()["head"]
    if head<start_frame:
        raise NativeRPGBridgeError("selected RPG frame outside observed native journal")
    through=min(head,start_frame+limit-1)
    replay=journal.replay(through=through)
    if replay["verified_frames"]!=through+1:
        raise NativeRPGBridgeError("incomplete verified source frame prefix")
    flag_source=dict(flags or {})
    last_fired={}
    completed=set()
    previous=None
    entries=[]
    observed_hashes=[]
    page_hashes=[{
        "id":p.page_id,"priority":p.priority,
        "conditions":[c.__dict__ for c in p.conditions],
        "actions":[a.__dict__ for a in p.actions],
        "cooldown_ms":p.cooldown_ms,"repeat":p.repeat,"enabled":p.enabled,
        "required_flags":p.required_flags,
    } for p in pages]
    authored_digest=_digest(page_hashes)
    for index in range(through+1):
        native=journal.native_sample(index)
        if native is None:
            raise NativeRPGBridgeError("every selected frame must have real native source")
        frame,chunk=journal.load(index)
        if frame.fps!=native.get("fps"):
            raise NativeRPGBridgeError("native source timing differs from signed GDD")
        current=native_rpg_observations(native,actor_id=actor_id)
        decision=evaluate_environment_events(
            pages,current=current,previous=previous,
            flags=flag_source,now_ms=frame.time_ns//1_000_000,
            last_fired_ms=last_fired,completed_once=frozenset(completed))
        accepted=[]
        for candidate in decision.accepted:
            last_fired[candidate.page_id]=frame.time_ns//1_000_000
            completed.add(candidate.page_id)
            accepted.append({
                "page_id":candidate.page_id,"priority":candidate.priority,
                "event_evidence_digest":candidate.evidence_digest,
                "observations":list(candidate.observations),
                "actions":[a.__dict__ for a in candidate.actions],
                "authority":"proposal_only_no_world_mutation",
            })
        source_digest=_digest(native)
        observed_hashes.append((frame.receipt_digest,source_digest))
        if index>=start_frame:
            result={
                "frame":index,
                "clock_ns":frame.time_ns,
                "signed_gdd_digest":journal.gdd.source_digest,
                "frame_receipt_digest":frame.receipt_digest,
                "chunk_evidence_digest":chunk["receipt_digest"],
                "native_source_digest":source_digest,
                "source_actor_id":actor_id,
                "observations":current,
                "accepted_proposals":accepted,
                "suppressed_pages":list(decision.suppressed),
                "missing_signals":list(decision.missing_signals),
                "requires_runtime_approval":True,
            }
            result["receipt_digest"]=_digest(result)
            entries.append(result)
        previous=current
    report={
        "schema":"skeleton.game.native_rpg_event_timeline.v1",
        "track":journal.track,"actor_id":actor_id,
        "signed_gdd_digest":journal.gdd.source_digest,
        "authored_pages_digest":authored_digest,
        "start_frame":start_frame,"through_frame":through,
        "source_prefix_verified_frames":replay["verified_frames"],
        "entries":entries,
        "candidate_fire_count":sum(len(e["accepted_proposals"]) for e in entries),
        "last_fired_clocks_ms":last_fired,
        "completed_once_page_ids":sorted(completed),
        "source_prefix_digest":_digest(observed_hashes),
        "authority":"source_replayed_RPG_proposals_not_approved_world_actions",
    }
    report["receipt_digest"]=_digest(report)
    return report
