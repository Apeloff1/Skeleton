"""Re-execute the existing Jeeves P0-P3 / session / campaign owner stack.

This proves deterministic candidate contracts over explicitly supplied
metadata, never independent physical reconstruction, GPU, or model inference.
"""
from __future__ import annotations

from dataclasses import asdict

from skeleton.app.recovered_evidence import (
    EvidenceError, array, fields, identifier, integer, text, digest, canonical, HEX,
)
from skeleton.jeeves.game_frontier_dynamics import PresentationClock
from skeleton.jeeves.game_frontier_p1_worldmodel import WorldModelEvidence
from skeleton.jeeves.game_frontier_session import FrontierSession
from skeleton.jeeves.game_frontier_campaign import CampaignLedger, audit_receipt
from skeleton.jeeves.game_frontier_milestone_8 import export_campaign

SCHEMA="skeleton.frontier-campaign.order.v1"
MAX_SESSIONS=32
MAX_SESSION_STEPS=128
MAX_CAMPAIGN_STEPS=512
MAX_ORDER_BYTES=512*1024


def sha(value):
    if type(value) is not str or HEX.fullmatch(value) is None:
        raise EvidenceError("lowercase SHA-256 evidence required")
    return value


def identity(value):
    value=identifier(value)
    if len(value)>80:
        raise EvidenceError("frontier identity exceeds owner ceiling")
    return value


def build_campaign(order):
    fields(order,{"schema","campaign_id","sessions"})
    if order["schema"]!=SCHEMA or len(canonical(order))>MAX_ORDER_BYTES:
        raise EvidenceError("unsupported or oversized frontier campaign")
    ledger=CampaignLedger(identity(order["campaign_id"]))
    seen=set()
    steps=0
    evidence=[]
    for spec in array(order["sessions"],1,MAX_SESSIONS):
        fields(spec,{"session_id","steps"})
        sid=identity(spec["session_id"])
        if sid in seen:
            raise EvidenceError("repeated session identity")
        seen.add(sid)
        session=FrontierSession(sid)
        rows=array(spec["steps"],1,MAX_SESSION_STEPS)
        steps+=len(rows)
        if steps>MAX_CAMPAIGN_STEPS:
            raise EvidenceError("campaign step ceiling")
        for row in rows:
            fields(row,{"fps","lod_tier","weather_digest","world","percepts","goal"})
            world=fields(row["world"],{"source_digest","mesh_vertex_count","mesh_triangle_count",
                                       "reconstruction_digest","adapter_id"})
            model=WorldModelEvidence(sha(world["source_digest"]),
                integer(world["mesh_vertex_count"],3,100_000_000),
                integer(world["mesh_triangle_count"],1,200_000_000),
                sha(world["reconstruction_digest"]),identity(world["adapter_id"]))
            clock=PresentationClock(integer(row["fps"],1,120))
            admission=session.step(clock=clock,lod_tier=integer(row["lod_tier"],0,4),
                weather_digest=sha(row["weather_digest"]),evidence=model,
                percepts=tuple(text(item,120) for item in array(row["percepts"],1,64)),
                goal=text(row["goal"],256))
            evidence.append(admission.admission_digest)
        if not session.verify():
            raise EvidenceError("canonical frontier session did not verify")
        ledger.add(session)
    if not ledger.verify():
        raise EvidenceError("canonical campaign did not verify")
    export=export_campaign(ledger,audit_receipt(ledger))
    return export,{"order_digest":digest(order),"export":asdict(export),"step_count":steps,
                   "admissions_digest":digest(evidence),
                   "node_candidate_contracts_executed":steps*4,
                   "model_inference_executed":False,"physical_world_reconstructed":False}
