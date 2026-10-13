"""Durable owner-scoped original living world saves with HMAC integrity.

The existing operator-configured SQLite storage keeps approved, server-
verified game state longer than a seven-day session token. There are
bounded save slots, owner isolation, exact-world identity checks and
optimistic concurrency to prevent stale clients overwriting newer
postgame decisions. No user-supplied SQL, scripts or arbitrary world files.
"""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import hmac
import json
import sqlite3
import time

from .dragon_living_world import (
    LivingWorld,LivingState,validate_world,validate_state,
    _canonical,describe,_sha,
)
from .dragon_living_world_checkpoint import (
    _secret,_owner,_time,_state,seal_checkpoint,
)

SCHEMA="skeleton.ai.dragon.durable_living_world_save.v1"
MAX_SLOTS=10
MAX_BYTES=8000

DDL="""
CREATE TABLE IF NOT EXISTS dragon_original_living_world_save_v1(
  owner TEXT NOT NULL,
  slot INTEGER NOT NULL CHECK(slot >= 0 AND slot < 10),
  world_fingerprint TEXT NOT NULL,
  document BLOB NOT NULL,
  mac TEXT NOT NULL,
  version INTEGER NOT NULL CHECK(version >= 1),
  updated_at INTEGER NOT NULL,
  PRIMARY KEY(owner,slot)
)
"""


def _slot(slot):
    if type(slot) is not int or not 0<=slot<MAX_SLOTS:
        raise ValueError("original world durable save slot outside 0..9")


def _database(db:sqlite3.Connection):
    if not isinstance(db,sqlite3.Connection):
        raise ValueError("original world save requires operator-configured SQLite")
    db.execute(DDL)


def _record(world:LivingWorld,state:LivingState,owner:str)->bytes:
    validate_world(world);validate_state(world,state);_owner(owner)
    document={
        "schema":SCHEMA,"owner":owner,
        "world_fingerprint":world.world_fingerprint,
        "world_id":world.world_id,"variation":world.variant,
        "style":world.style,"lifecycle":world.lifecycle,
        "player":asdict(state),
        "player_history_digest":state.history_digest,
    }
    blob=_canonical(document)
    if len(blob)>MAX_BYTES:
        raise ValueError("original world durable save exceeds bounded record capacity")
    return blob


def _mac(blob:bytes)->str:
    return hmac.new(_secret(),blob,sha256).hexdigest()


def store(db:sqlite3.Connection,world:LivingWorld,state:LivingState,
          owner:str,slot:int,*,expected_digest:str|None=None,
          replace_existing:bool=False,now:int|None=None)->dict:
    _slot(slot)
    stamp=_time(now)
    blob=_record(world,state,owner)
    if type(replace_existing) is not bool or (
        expected_digest is not None and (
            type(expected_digest) is not str or
            len(expected_digest)!=64 or
            any(x not in "0123456789abcdef" for x in expected_digest)
        )
    ):
        raise ValueError("optimistic save replacement claim malformed")
    _database(db)
    old=db.execute(
        "SELECT world_fingerprint,document,mac,version FROM "
        "dragon_original_living_world_save_v1 WHERE owner=? AND slot=?",
        (owner,slot),
    ).fetchone()
    if old:
        previous=bytes(old[1])
        if not hmac.compare_digest(_mac(previous),old[2]):
            raise PermissionError("durable original world save integrity changed")
        if not replace_existing:
            raise FileExistsError("original world save slot already contains a game")
        old_doc=json.loads(previous)
        if old_doc.get("world_fingerprint")!=world.world_fingerprint:
            raise PermissionError("saving another world into an occupied slot requires new slot")
        if expected_digest is None or (
            expected_digest!=old_doc.get("player_history_digest")
        ):
            raise FileExistsError("stale save version would overwrite another player decision")
        version=old[3]+1
        changed=db.execute(
            "UPDATE dragon_original_living_world_save_v1 SET "
            "document=?,mac=?,version=?,updated_at=? "
            "WHERE owner=? AND slot=? AND version=?",
            (blob,_mac(blob),version,stamp,owner,slot,old[3]),
        )
        if changed.rowcount!=1:
            raise FileExistsError("another writer advanced this game save slot")
    else:
        if expected_digest is not None or replace_existing:
            raise ValueError("cannot replace a durable original save before it exists")
        version=1
        db.execute(
            "INSERT INTO dragon_original_living_world_save_v1 "
            "(owner,slot,world_fingerprint,document,mac,version,updated_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (owner,slot,world.world_fingerprint,blob,_mac(blob),version,stamp),
        )
    db.commit()
    return {
        "schema":SCHEMA,"status":"durably_saved_original_game_state",
        "slot":slot,"version":version,
        "owner_scoped":True,
        "world_fingerprint":world.world_fingerprint,
        "history_digest":state.history_digest,
        "actions_played":state.actions_played,
        "continues_after_ending":world.allows_continuation,
        "claim":"server SQLite save is integrity-checked and can be reissued "
                "as a renewable signed checkpoint; not publication clearance",
    }


def restore(db:sqlite3.Connection,world:LivingWorld,owner:str,slot:int,
            *,now:int|None=None)->dict:
    _slot(slot)
    validate_world(world);_owner(owner)
    _database(db)
    row=db.execute(
        "SELECT world_fingerprint,document,mac,version,updated_at "
        "FROM dragon_original_living_world_save_v1 "
        "WHERE owner=? AND slot=?",
        (owner,slot),
    ).fetchone()
    if row is None:
        raise FileNotFoundError("owner has not saved an original game in this slot")
    if row[0]!=world.world_fingerprint:
        raise PermissionError("original save belongs to another world or variant")
    blob=bytes(row[1])
    if len(blob)>MAX_BYTES or not hmac.compare_digest(_mac(blob),row[2]):
        raise PermissionError("original game save receipt is missing or corrupted")
    document=json.loads(blob)
    if set(document)!={
        "schema","owner","world_fingerprint","world_id","variation",
        "style","lifecycle","player","player_history_digest",
    } or document["schema"]!=SCHEMA or (
        document["owner"]!=owner or
        document["world_fingerprint"]!=world.world_fingerprint or
        document["world_id"]!=world.world_id or
        document["variation"]!=world.variant or
        document["style"]!=world.style or
        document["lifecycle"]!=world.lifecycle
    ):
        raise PermissionError("durable original save signature has changed source")
    state=_state(document["player"])
    validate_state(world,state)
    if state.history_digest!=document["player_history_digest"]:
        raise PermissionError("restored story ending evidence chain does not match")
    token=seal_checkpoint(world,state,owner,now=now)
    return {
        "schema":SCHEMA,"status":"durable_original_game_restored",
        "slot":slot,"version":row[3],"updated_at":row[4],
        "world_fingerprint":world.world_fingerprint,
        "history_digest":state.history_digest,
        "state":asdict(state),
        "new_checkpoint":token,
        "scope":"durable operator SQLite storage, signed renewable player continuation",
    }


def list_saves(db:sqlite3.Connection,owner:str,*,limit:int=10)->tuple[dict,...]:
    _owner(owner)
    if type(limit) is not int or not 1<=limit<=MAX_SLOTS:
        raise ValueError("original world save listing limit outside 1..10")
    _database(db)
    rows=db.execute(
        "SELECT slot,world_fingerprint,version,updated_at "
        "FROM dragon_original_living_world_save_v1 "
        "WHERE owner=? ORDER BY slot LIMIT ?",
        (owner,limit),
    ).fetchall()
    return tuple({
        "slot":row[0],"world_fingerprint":row[1],
        "version":row[2],"updated_at":row[3],
    } for row in rows)
