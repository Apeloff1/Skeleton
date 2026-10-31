"""Objective two-pass acceptance for original Godot expedition candidates.

Distinct evidence methods re-evaluate game connectivity and complete
individual authored actions. Product release stays blocked without independently
verified engine provenance and rights review. Hashes are evidence checksums,
not signatures or claims of copyright ownership.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Mapping

from .game_frontier_expedition import (
    ExpeditionAction, ExpeditionEpisode, ExpeditionError, ExpeditionWorld,
    Traveler, find_route, verify_route, _digest, _json,
)
from .game_frontier_expedition_godot import verify_expedition_godot_project
from .game_frontier_expedition_qa import SCHEMA as QA_SCHEMA

SCHEMA="skeleton.game.frontier_expedition_release_review.v1"
_REQUIRED_AXES=(
    "source_closure","gameplay_viability","independent_replay",
    "multiscenario_coverage","asset_lineage","originality_review",
    "copyright_review","native_validation",
)


@dataclass(frozen=True,slots=True)
class ExternalContentReview:
    """Explicit host-provided reviewer assertion, never an AI-generated permit."""
    kind: str
    reviewer_id: str
    source_digest: str
    verdict: str
    evidence_ref: str
    evidence_sha256: str

    def __post_init__(self):
        if self.kind not in {"copyright","originality"}:
            raise ExpeditionError("content reviewer role must be explicit")
        if (not isinstance(self.reviewer_id,str)
                or not 3<=len(self.reviewer_id)<=128
                or not isinstance(self.evidence_ref,str)
                or not 3<=len(self.evidence_ref)<=256):
            raise ExpeditionError("content review needs independent host evidence")
        if self.verdict not in {"approved","rejected"}:
            raise ExpeditionError("content verdict must be explicit")
        for item in (self.source_digest,self.evidence_sha256):
            if not isinstance(item,str) or len(item)!=64 or any(
                ch not in "0123456789abcdef" for ch in item
            ):
                raise ExpeditionError("review content source must be SHA-256 pinned")


def _source_qa_report(report: Mapping, world: ExpeditionWorld)->dict:
    if not isinstance(report,Mapping) or report.get("schema")!=QA_SCHEMA:
        raise ExpeditionError("multi-scenario original QA report required")
    snapshot=dict(report)
    receipt=snapshot.pop("receipt_digest",None)
    if receipt!=_digest(snapshot):
        raise ExpeditionError("QA report root receipt invalid")
    if (report.get("source_digest")!=world.source_digest
            or report.get("project")!=world.project_id
            or type(report.get("cases_executed")) is not int
            or report["cases_executed"]<1 or report["cases_executed"]>512
            or not isinstance(report.get("cases"),list)
            or len(report["cases"])!=report["cases_executed"]):
        raise ExpeditionError("QA report source or scenario coverage contradicts game")
    for row in report["cases"]:
        if type(row) is not dict or row.get("receipt_digest")!=_digest({
            key:value for key,value in row.items() if key!="receipt_digest"
        }):
            raise ExpeditionError("QA case evidence altered")
        if (type(row.get("routes_executed")) is not int
                or not 0<=row["routes_executed"]<=8
                or type(row.get("blocked")) is not bool
                or row["blocked"]==(row["routes_executed"]>0)
                or len(row.get("route_receipts",[]))!=row["routes_executed"]):
            raise ExpeditionError("QA scenario contradicted executed routes")
    if sum(r["routes_executed"] for r in report["cases"])!=report["executed_game_routes"]:
        raise ExpeditionError("QA aggregate does not match scenario receipts")
    return dict(report)


def _independent_gameplay_check(world:ExpeditionWorld,player:Traveler)->dict:
    """Reconstruct an actual winning path without calling the route verifier."""
    route=find_route(world,player,world.destinations[0])
    episode=ExpeditionEpisode(world,player)
    transitions=[]
    for eid in route.edge_ids:
        event=episode.step(ExpeditionAction("travel",eid))
        if event["state"]["position"]!=world.by_edge[eid].target:
            raise ExpeditionError("independent reviewer observed inconsistent movement")
        transitions.append(event["receipt"])
    if not episode.won or len(transitions)!=len(route.edge_ids):
        raise ExpeditionError("independent reviewer did not complete the game")
    return {
        "source":world.digest,"steps":len(transitions),
        "terminal_position":episode.position,
        "receipt_head":episode.snapshot()["receipt_head"],
        "victory":True,
    }


def evaluate_expedition_release(
    world:ExpeditionWorld,traveler:Traveler,files:Mapping[str,str],
    qa_report:Mapping, *,
    native_report:Mapping | None=None,
    copyright_review:ExternalContentReview | None=None,
    originality_review:ExternalContentReview | None=None,
)->dict:
    """Reproduce release candidate proof; never manufacture host authorization."""
    if not isinstance(world,ExpeditionWorld) or not isinstance(traveler,Traveler):
        raise ExpeditionError("actual original game source required")
    packaged=verify_expedition_godot_project(
        files,world,traveler,include_autoplay=(
            "game/frontier/autoplay.json" in files
        ),
    )
    qa=_source_qa_report(qa_report,world)
    route=find_route(world,traveler,world.destinations[0])
    primary=verify_route(world,traveler,route)
    independent=_independent_gameplay_check(world,traveler)
    if (not primary["verified"] or not primary["final_state"]["won"]
            or independent["source"]!=world.digest
            or primary["receipt_head"]!=independent["receipt_head"]
            or len(primary["step_receipts"])!=independent["steps"]):
        raise ExpeditionError("independent gameplay acceptance differs from first verifier")
    audit={}
    for kind,review in (("copyright",copyright_review),("originality",originality_review)):
        if review is None:
            audit[kind]={"status":"missing"}
            continue
        if not isinstance(review,ExternalContentReview) or review.kind!=kind:
            raise ExpeditionError("content review role was substituted")
        if review.source_digest!=world.source_digest:
            raise ExpeditionError("content review signs another source snapshot")
        audit[kind]={
            "status":review.verdict,
            "reviewer_id":review.reviewer_id,
            "evidence_ref":review.evidence_ref,
            "evidence_digest":review.evidence_sha256,
        }
    if copyright_review is not None and originality_review is not None:
        if (copyright_review.reviewer_id==originality_review.reviewer_id
                or copyright_review.evidence_sha256==originality_review.evidence_sha256):
            raise ExpeditionError("creative and rights checks require independent evidence")
    native_ok=False
    if native_report is not None:
        if (not isinstance(native_report,Mapping)
                or native_report.get("schema")!="skeleton.game.expedition_native_complete_replay.v1"
                or native_report.get("world_digest")!=world.digest
                or native_report.get("source_digest")!=world.source_digest
                or native_report.get("candidate_files_receipt")!=packaged["receipt_digest"]
                or native_report.get("native_process_executed") is not True
                or native_report.get("native_gameplay_consistent") is not True
                or native_report.get("completed") is not True
                or native_report.get("receipt_digest")!=_digest({
                    key:value for key,value in native_report.items() if key!="receipt_digest"
                })):
            raise ExpeditionError("native execution report is stale or contradictory")
        native_ok=True
    axes={
        "source_closure":True,
        "gameplay_viability":True,
        "independent_replay":True,
        "multiscenario_coverage":qa["executed_game_routes"]>0,
        "asset_lineage":bool(packaged["file_hashes"]),
        "originality_review":audit["originality"]["status"]=="approved",
        "copyright_review":audit["copyright"]["status"]=="approved",
        "native_validation":native_ok,
    }
    missing=tuple(key for key in _REQUIRED_AXES if not axes[key])
    report={
        "schema":SCHEMA,"project_id":world.project_id,
        "source_digest":world.source_digest,"world_digest":world.digest,
        "candidate_receipt":packaged["receipt_digest"],
        "primary_gameplay_receipt":primary["receipt_head"],
        "independent_gameplay_receipt":independent["receipt_head"],
        "qa_receipt":qa["receipt_digest"],
        "axes":axes,"axis_count":len(axes),
        "passed_axes":sum(axes.values()),
        "blocked_axes":list(missing),
        "content_reviews":audit,
        "native_candidate_receipt":(
            native_report["receipt_digest"] if native_ok else None),
        "status":"review_candidate_ready" if not missing else "blocked",
        "independent_host_authorization_verified":False,
        "external_legal_clearance_verified":False,
        "production_release_approved":False,
        "original_100_masterplan_milestones_complete":False,
    }
    report["receipt_digest"]=_digest(report)
    return report
