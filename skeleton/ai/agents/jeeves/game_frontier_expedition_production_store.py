"""Durable longform game-production journal: gameplay, canon, quests and endings.

A crash or agent restart must never lose source events or invent a story flag.
Every loaded snapshot is re-executed through the actual game/story/quest
directors. SQLite CAS plus hash-linked generations prevents silent lost updates.
Receipts are checksums, not externally anchored signatures.
"""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
import json
import re
import sqlite3
from typing import Mapping

from .game_frontier_expedition import (
    ExpeditionError,ExpeditionWorld,Traveler,_json,_digest,
)
from .game_frontier_expedition_narrative import StoryBook
from .game_frontier_expedition_quests import QuestBook
from .game_frontier_expedition_session import ProductionSession

_KEY=re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
_MAX_BYTES=4_000_000


class ProductionSessionConflict(ExpeditionError):
    pass


class ProductionSessionStore:
    def __init__(self,path:Path):
        if not isinstance(path,Path):
            raise ExpeditionError("production journal needs an explicit durable filesystem path")
        path.parent.mkdir(parents=True,exist_ok=True)
        self._db=sqlite3.connect(
            str(path),timeout=15,isolation_level=None,
            check_same_thread=False,
        )
        self._db.execute("PRAGMA busy_timeout=15000")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS production_head(
                run_id TEXT PRIMARY KEY,
                version INTEGER NOT NULL,
                world_digest TEXT NOT NULL,
                story_digest TEXT NOT NULL,
                quest_digest TEXT NOT NULL,
                game_profile TEXT NOT NULL,
                payload BLOB NOT NULL,
                bytes_sha256 TEXT NOT NULL,
                receipt TEXT NOT NULL
            )""")
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS production_history(
                run_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                previous TEXT NOT NULL,
                bytes_sha256 TEXT NOT NULL,
                receipt TEXT NOT NULL,
                PRIMARY KEY(run_id,version)
            )""")
        self._closed=False

    def _scope(self,run_id):
        if self._closed:
            raise ExpeditionError("production journal has been closed")
        if type(run_id) is not str or not _KEY.fullmatch(run_id):
            raise ExpeditionError("invalid source-scoped game production run id")

    def _history(self,run_id,row):
        values=self._db.execute(
            "SELECT version,previous,bytes_sha256,receipt FROM production_history "
            "WHERE run_id=? ORDER BY version",(run_id,),
        ).fetchall()
        if (row is None)!=(len(values)==0):
            raise ExpeditionError("production journal history is missing")
        prior="0"*64
        for i,(version,previous,blobhash,receipt) in enumerate(values,1):
            if i!=version or previous!=prior:
                raise ExpeditionError("production journal generations out of sequence")
            candidate=_digest({"run":run_id,"version":version,
                               "previous":prior,"bytes":blobhash})
            if candidate!=receipt:
                raise ExpeditionError("production journal receipt was altered")
            prior=receipt
        if row is not None and (
            row[1]!=len(values) or
            row[8]!=prior or row[7]!=values[-1][2]
        ):
            raise ExpeditionError("production head was replaced or rolled back")
        return prior

    def _checked(self,run_id,world,traveler,story,quests):
        self._scope(run_id)
        if not isinstance(world,ExpeditionWorld) or not isinstance(traveler,Traveler):
            raise ExpeditionError("game production journal needs typed source/player")
        if not isinstance(story,StoryBook) or not isinstance(quests,QuestBook):
            raise ExpeditionError("game production journal needs canonical story/quest")
        return ProductionSession(world,traveler,story,quests)

    def load(self,run_id:str,world:ExpeditionWorld,traveler:Traveler,
             story:StoryBook,quests:QuestBook)->tuple[int,ProductionSession,str]|None:
        baseline=self._checked(run_id,world,traveler,story,quests)
        self._db.execute("BEGIN")
        try:
            row=self._db.execute(
                "SELECT * FROM production_head WHERE run_id=?",(run_id,),
            ).fetchone()
            self._history(run_id,row)
            if row is None:
                self._db.execute("COMMIT")
                return None
            if (row[2]!=world.digest or row[3]!=story.digest
                    or row[4]!=quests.digest or row[5]!=baseline.game.traveler_digest):
                raise ExpeditionError("production journal belongs to a foreign source")
            raw=row[6]
            if (not isinstance(raw,bytes) or len(raw)>_MAX_BYTES
                    or sha256(raw).hexdigest()!=row[7]):
                raise ExpeditionError("production journal bytes were altered")
            try:
                payload=json.loads(raw)
                if _json(payload,_MAX_BYTES)!=raw:
                    raise ExpeditionError("production payload JSON was not canonical")
                reproduced=ProductionSession.restore(world,traveler,story,quests,payload)
            except (ValueError,TypeError,UnicodeError) as exc:
                raise ExpeditionError("production journal could not be replayed") from exc
            self._db.execute("COMMIT")
            return row[1],reproduced,row[8]
        except Exception:
            self._db.execute("ROLLBACK")
            raise

    def save(self,run_id:str,session:ProductionSession,*,
             expected_version:int|None=None)->tuple[int,str]:
        if not isinstance(session,ProductionSession):
            raise ExpeditionError("production journal requires real source session")
        world=session.game.world
        traveler=session.game.traveler
        story=session.story.book
        quests=session.quests.book
        baseline=self._checked(run_id,world,traveler,story,quests)
        if expected_version is not None and (
            type(expected_version) is not int or expected_version<1):
            raise ExpeditionError("production optimistic generation invalid")
        checked=ProductionSession.restore(
            world,traveler,story,quests,session.snapshot(),
        )
        raw=_json(checked.snapshot(),_MAX_BYTES)
        checksum=sha256(raw).hexdigest()
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row=self._db.execute(
                "SELECT * FROM production_head WHERE run_id=?",(run_id,),
            ).fetchone()
            prior=self._history(run_id,row)
            if row is None:
                if expected_version is not None:
                    raise ProductionSessionConflict("source production checkpoint missing")
                version=1
            else:
                if (row[2]!=world.digest or row[3]!=story.digest or
                        row[4]!=quests.digest or row[5]!=baseline.game.traveler_digest):
                    raise ProductionSessionConflict("production game/story source changed")
                if row[7]==checksum and row[6]==raw:
                    self._db.execute("COMMIT")
                    return row[1],row[8]
                if row[1]!=expected_version:
                    raise ProductionSessionConflict("production journal advanced after read")
                if sha256(row[6]).hexdigest()!=row[7]:
                    raise ExpeditionError("existing production head was modified")
                old=ProductionSession.restore(
                    world,traveler,story,quests,json.loads(row[6]),
                )
                if (len(session.events)<len(old.events) or
                        session.events[:len(old.events)]!=old.events):
                    raise ProductionSessionConflict("production event history cannot rewind")
                version=row[1]+1
            receipt=_digest({"run":run_id,"version":version,
                             "previous":prior,"bytes":checksum})
            if row is None:
                self._db.execute(
                    "INSERT INTO production_head VALUES(?,?,?,?,?,?,?,?,?)",
                    (run_id,version,world.digest,story.digest,quests.digest,
                     baseline.game.traveler_digest,raw,checksum,receipt),
                )
            else:
                self._db.execute(
                    "UPDATE production_head SET version=?,payload=?,bytes_sha256=?,"
                    "receipt=? WHERE run_id=?",
                    (version,raw,checksum,receipt,run_id),
                )
            self._db.execute(
                "INSERT INTO production_history VALUES(?,?,?,?,?)",
                (run_id,version,prior,checksum,receipt),
            )
            self._db.execute("COMMIT")
            return version,receipt
        except Exception:
            self._db.execute("ROLLBACK")
            raise

    def history(self,run_id:str)->tuple[dict,...]:
        self._scope(run_id)
        row=self._db.execute(
            "SELECT * FROM production_head WHERE run_id=?",(run_id,),
        ).fetchone()
        self._history(run_id,row)
        values=self._db.execute(
            "SELECT version,previous,receipt FROM production_history "
            "WHERE run_id=? ORDER BY version",(run_id,),
        ).fetchall()
        return tuple({"version":v,"previous":p,"receipt":r} for v,p,r in values)

    def close(self):
        if not self._closed:
            self._db.close()
            self._closed=True

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.close()
