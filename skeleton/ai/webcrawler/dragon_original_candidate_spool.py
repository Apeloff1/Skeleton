"""Bounded, resumable local production of ORIGINAL playable game candidates.

4.29b design addresses cannot be placed into one in-memory Python list.
This exact-index SQLite spool retains genuinely materialized source-game
prototypes with verified dual-runtime gameplay, source hashes, provenance
and an explicit NOT RELEASED status.

Each call processes at most 128 original games, in one atomic transaction.
Repeated calls are idempotent ONLY after independently rematerializing and
checking existing candidate receipts. Chunked CLI calls can traverse
millions of addresses over time, without claiming that such a batch was
actually executed by this assistant.

No arbitrary network crawler execution, external media copying, automatic
distribution, source code evaluation, or commercial ROM import.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import argparse,json,os,sqlite3,sys
from pathlib import Path

from .dragon_original_prototype_factory import (
    SCHEMA as PROTOTYPE_SCHEMA,materialize,verify_prototype,
)
from .dragon_original_mechanic_forge import FULL_BINARY_PROFILE_COUNT

SCHEMA="skeleton.ai.dragon.original_candidate_spool.v1"
MAX_BATCH=128
DDL="""
CREATE TABLE IF NOT EXISTS dragon_original_candidate_v1(
   original_nucleus INTEGER PRIMARY KEY,
   gameplay_source_digest TEXT NOT NULL,
   playable_world_digest TEXT NOT NULL,
   content_sha256 TEXT NOT NULL,
   source_receipt TEXT NOT NULL,
   candidate_status TEXT NOT NULL DEFAULT 'underbuilt_source_draft'
      CHECK(candidate_status IN ('source_playable_only','underbuilt_source_draft')),
   CHECK(original_nucleus>=0 AND original_nucleus<4294967296)
)
"""


def _request(start:int,count:int,routes:int,steps:int,seed:int):
    if (type(start) is not int or not 0<=start<FULL_BINARY_PROFILE_COUNT
            or type(count) is not int or not 1<=count<=MAX_BATCH or
            start+count>FULL_BINARY_PROFILE_COUNT or
            type(routes) is not int or not 1<=routes<=4 or
            type(steps) is not int or not 4<=steps<=24 or
            type(seed) is not int or not 0<=seed<2**32):
        raise ValueError("original game candidate spool requires bounded, typed indices")


def _canonical(obj)->str:
    return json.dumps(obj,sort_keys=True,separators=(",",":"),
                      ensure_ascii=True)


def _sha(raw:str)->str:
    return sha256(raw.encode("utf-8")).hexdigest()


def _open(db:sqlite3.Connection):
    if not isinstance(db,sqlite3.Connection):
        raise ValueError("original candidate spool requires local SQLite")
    db.execute(DDL)


def materialize_batch(
    db:sqlite3.Connection,*,start:int,count:int,
    routes:int=2,steps:int=12,branch_seed:int=0,
)->dict:
    _request(start,count,routes,steps,branch_seed)
    _open(db)
    written=0
    genuinely_playable=0
    underbuilt=0
    verified=0
    chain=[]
    # SQLite context manager makes the *entire batch* atomic. It never
    # silently replaces existing content or accepts a forged prior receipt.
    with db:
        db.execute("BEGIN IMMEDIATE")
        for index in range(start,start+count):
            candidate=materialize(
                index,branch_seed=branch_seed,
                routes=routes,steps=steps)
            if not verify_prototype(candidate,branch_seed=branch_seed)["verified"]:
                raise ValueError("original game failed independent gameplay verification")
            receipt=_canonical(asdict(candidate))
            digest=_sha(receipt)
            candidate_status=(
                "source_playable_only" if candidate.core_loop_viable
                else "underbuilt_source_draft")
            row=db.execute(
                "SELECT gameplay_source_digest,playable_world_digest,"
                "content_sha256,source_receipt,candidate_status "
                "FROM dragon_original_candidate_v1 WHERE original_nucleus=?",
                (index,),
            ).fetchone()
            if row:
                if row!=(
                    candidate.source_digest,candidate.world_source_digest,
                    digest,receipt,candidate_status,
                ):
                    raise PermissionError(
                        "original game candidate already exists with another "
                        "gameplay source, environmental seed or receipt")
                verified+=1
            else:
                db.execute(
                    "INSERT INTO dragon_original_candidate_v1 "
                    "(original_nucleus,gameplay_source_digest,"
                    "playable_world_digest,content_sha256,"
                    "source_receipt,candidate_status) "
                    "VALUES(?,?,?,?,?,?)",
                    (index,candidate.source_digest,
                     candidate.world_source_digest,digest,receipt,
                     candidate_status),
                )
                written+=1
                if candidate.core_loop_viable:
                    genuinely_playable+=1
                else:
                    underbuilt+=1
            chain.append((index,digest))
    return {
        "schema":SCHEMA,"requested":count,
        "new_original_source_candidates":written,
        "new_original_playable_prototypes":genuinely_playable,
        "new_underbuilt_drafts":underbuilt,
        "independently_verified_existing_prototypes":verified,
        "start":start,"end_exclusive":start+count,
        "content_chain_sha256":_sha(_canonical(chain)),
        "database_total_materialized":db.execute(
            "SELECT COUNT(*) FROM dragon_original_candidate_v1"
        ).fetchone()[0],
        "genuinely_finished_licensed_games":0,
        "claim":"materialized source-playable prototypes only; "
                "not published, device-built or copyright-reviewed games",
    }


def audit_batch(db:sqlite3.Connection,*,start:int,count:int,
                branch_seed:int=0)->dict:
    if (type(start) is not int or type(count) is not int or
            not 0<=start<FULL_BINARY_PROFILE_COUNT or
            not 1<=count<=MAX_BATCH or
            start+count>FULL_BINARY_PROFILE_COUNT):
        raise ValueError("original candidate batch audit outside bounds")
    _open(db)
    rows=db.execute(
        "SELECT original_nucleus,content_sha256,source_receipt,candidate_status "
        "FROM dragon_original_candidate_v1 "
        "WHERE original_nucleus>=? AND original_nucleus<? "
        "ORDER BY original_nucleus",
        (start,start+count),
    ).fetchall()
    if len(rows)!=count:
        raise ValueError("original candidate evidence batch incomplete")
    for number,digest,document,status in rows:
        if (status not in ("source_playable_only","underbuilt_source_draft")
                or _sha(document)!=digest):
            raise PermissionError("original source game receipt was altered")
        claim=json.loads(document)
        if claim.get("original_nucleus")!=number or claim.get("schema")!=PROTOTYPE_SCHEMA:
            raise PermissionError("game proof belongs to a different candidate")
        route_list=claim.get("replayed_journeys")
        if (not isinstance(route_list,list) or not route_list or
                not isinstance(route_list[0],dict) or
                not isinstance(route_list[0].get("actions"),list)):
            raise PermissionError("original source gameplay proof absent")
        fresh=materialize(
            number,branch_seed=branch_seed,
            routes=len(route_list),
            steps=len(route_list[0]["actions"]),
        )
        if (("source_playable_only" if fresh.core_loop_viable
             else "underbuilt_source_draft")!=status):
            raise PermissionError("saved candidate deceptively claims playable quality")
        if _canonical(asdict(fresh))!=document:
            raise PermissionError(
                "original candidate source, choices, outcomes or world changed"
            )
    return {
        "schema":SCHEMA,"verified":count,
        "start":start,"end_exclusive":start+count,
        "all_actual_original_gameplay_replayed":True,
        "published_games_certified":0,
    }


def _cli():
    parser=argparse.ArgumentParser(
        description="Local original game candidate production, explicit source-only consent")
    parser.add_argument("--db",required=True)
    parser.add_argument("--start",required=True,type=int)
    parser.add_argument("--count",required=True,type=int)
    parser.add_argument("--routes",type=int,default=2)
    parser.add_argument("--steps",type=int,default=12)
    parser.add_argument("--seed",type=int,default=0)
    parser.add_argument("--authorized-local",action="store_true")
    parser.add_argument("--verify",action="store_true")
    args=parser.parse_args()
    if not args.authorized_local:
        parser.error("candidate generation needs explicit local authorization")
    path=Path(args.db).expanduser()
    if path.is_symlink() or not path.parent.is_dir():
        parser.error("original game database path must have a real existing parent")
    _request(args.start,args.count,args.routes,args.steps,args.seed)
    with sqlite3.connect(str(path),timeout=10) as database:
        database.execute("PRAGMA busy_timeout=10000")
        result=materialize_batch(
            database,start=args.start,count=args.count,
            routes=args.routes,steps=args.steps,branch_seed=args.seed,
        )
        if args.verify:
            result["independent_audit"]=audit_batch(
                database,start=args.start,count=args.count,
                branch_seed=args.seed,
            )
        print(json.dumps(result,sort_keys=True,indent=2))


if __name__=="__main__":
    _cli()
