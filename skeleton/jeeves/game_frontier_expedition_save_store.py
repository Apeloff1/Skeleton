"""Durable source-bound expedition save games with verifiable replay and CAS.

All state comes from the canonical action ledger. SQLite stores bounded
snapshots, not arbitrary pickle, and every loaded step is independently
re-executed. Cross-process stale writes fail closed. Generation history
makes missing or reordered saves observable.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from threading import RLock

from .game_frontier_expedition import (
    ExpeditionEpisode, ExpeditionError, ExpeditionWorld, Traveler, _json,
)

_SCHEMA="skeleton.game.expedition_save_store.v1"
_KEY=re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")


class ExpeditionSaveError(ValueError):
    pass


class ExpeditionSaveConflict(ExpeditionSaveError):
    pass


@dataclass(frozen=True,slots=True)
class ExpeditionSave:
    run_id: str
    generation: int
    episode: ExpeditionEpisode
    snapshot_sha256: str
    receipt: str


def _receipt(run,version,source,snapshot,prior):
    return sha256(_json({
        "schema":_SCHEMA,"run":run,"version":version,
        "source":source,"snapshot":snapshot,"prior":prior,
    })).hexdigest()


class ExpeditionSaveStore:
    def __init__(self,path: str | Path):
        self.path=str(path)
        if self.path!=":memory:":
            Path(self.path).parent.mkdir(parents=True,exist_ok=True)
        self._lock=RLock()
        self._closed=False
        self._db=sqlite3.connect(
            self.path,timeout=15,isolation_level=None,check_same_thread=False,
        )
        self._db.row_factory=sqlite3.Row
        self._db.execute("PRAGMA busy_timeout=15000")
        if self.path!=":memory:":
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
        self._db.executescript("""
        CREATE TABLE IF NOT EXISTS expedition_save (
          run_id TEXT PRIMARY KEY,
          generation INTEGER NOT NULL,
          world_digest TEXT NOT NULL,
          traveler_digest TEXT NOT NULL,
          payload BLOB NOT NULL,
          payload_sha256 TEXT NOT NULL,
          receipt_digest TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS expedition_save_history (
          run_id TEXT NOT NULL,
          generation INTEGER NOT NULL,
          world_digest TEXT NOT NULL,
          payload_sha256 TEXT NOT NULL,
          previous_receipt TEXT NOT NULL,
          receipt_digest TEXT NOT NULL,
          PRIMARY KEY(run_id,generation)
        );
        """)

    def _check(self,key):
        if self._closed:
            raise ExpeditionSaveError("save store closed")
        if type(key) is not str or not _KEY.fullmatch(key):
            raise ExpeditionSaveError("invalid source-scoped run identity")

    def _history(self,key,row):
        history=self._db.execute(
            "SELECT * FROM expedition_save_history WHERE run_id=? ORDER BY generation",
            (key,),
        ).fetchall()
        if (row is None)!=(len(history)==0):
            raise ExpeditionSaveError("save generation history incomplete")
        previous="0"*64
        for number,event in enumerate(history,1):
            if event["generation"]!=number or event["previous_receipt"]!=previous:
                raise ExpeditionSaveError("save history was truncated or reordered")
            expected=_receipt(
                key,number,event["world_digest"],
                event["payload_sha256"],previous,
            )
            if event["receipt_digest"]!=expected:
                raise ExpeditionSaveError("save history was altered")
            previous=expected
        if row is not None and (
            row["generation"]!=len(history) or
            row["receipt_digest"]!=previous or
            row["world_digest"]!=history[-1]["world_digest"] or
            row["payload_sha256"]!=history[-1]["payload_sha256"]
        ):
            raise ExpeditionSaveError("save head differs from durable history")
        return previous

    def load(
        self,run_id:str,world:ExpeditionWorld,traveler:Traveler,
    )->ExpeditionSave | None:
        with self._lock:
            self._check(run_id)
            self._db.execute("BEGIN")
            try:
                row=self._db.execute(
                    "SELECT * FROM expedition_save WHERE run_id=?",(run_id,),
                ).fetchone()
                self._history(run_id,row)
                if row is None:
                    self._db.execute("COMMIT")
                    return None
                if row["world_digest"]!=world.digest:
                    raise ExpeditionSaveError("save belongs to another world source")
                payload=row["payload"]
                if not isinstance(payload,bytes) or len(payload)>2_000_000:
                    raise ExpeditionSaveError("save payload oversized or invalid")
                if sha256(payload).hexdigest()!=row["payload_sha256"]:
                    raise ExpeditionSaveError("save bytes failed integrity check")
                try:
                    snapshot=json.loads(payload)
                    if _json(snapshot,2_000_000)!=payload:
                        raise ExpeditionSaveError("saved JSON not canonical")
                    episode=ExpeditionEpisode.restore(world,traveler,snapshot)
                except (ValueError,TypeError,UnicodeError,ExpeditionError) as exc:
                    raise ExpeditionSaveError("gameplay replay failed on restore") from exc
                result=ExpeditionSave(
                    run_id,row["generation"],episode,row["payload_sha256"],
                    row["receipt_digest"],
                )
                self._db.execute("COMMIT")
                return result
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def save(
        self,run_id:str,episode:ExpeditionEpisode,
        *, expected_generation:int | None=None,
    )->ExpeditionSave:
        if not isinstance(episode,ExpeditionEpisode):
            raise ExpeditionSaveError("save requires actual gameplay episode")
        if expected_generation is not None and (
            type(expected_generation) is not int or expected_generation<1
        ):
            raise ExpeditionSaveError("save expected generation invalid")
        payload=_json(episode.snapshot(),2_000_000)
        source=episode.world.digest
        traveler=episode.traveler
        with self._lock:
            self._check(run_id)
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row=self._db.execute(
                    "SELECT * FROM expedition_save WHERE run_id=?",(run_id,),
                ).fetchone()
                prior=self._history(run_id,row)
                if row is None:
                    if expected_generation is not None:
                        raise ExpeditionSaveConflict("save generation absent")
                    generation=1
                else:
                    if row["world_digest"]!=source or row["traveler_digest"]!=episode.traveler_digest:
                        raise ExpeditionSaveConflict("save source or player changed")
                    # Old source bytes must also be genuinely replayable before overwrite.
                    if (not isinstance(row["payload"],bytes) or
                        sha256(row["payload"]).hexdigest()!=row["payload_sha256"]):
                        raise ExpeditionSaveError("previous save payload corrupted")
                    try:
                        old_episode=ExpeditionEpisode.restore(
                            episode.world,traveler,json.loads(row["payload"]))
                    except (ValueError,TypeError,ExpeditionError) as exc:
                        raise ExpeditionSaveError("previous game save cannot replay") from exc
                    if row["payload"]==payload:
                        self._db.execute("COMMIT")
                        return ExpeditionSave(
                            run_id,row["generation"],episode,
                            row["payload_sha256"],row["receipt_digest"],
                        )
                    if row["generation"]!=expected_generation:
                        raise ExpeditionSaveConflict("save advanced since last read")
                    # Never allow an old snapshot to truncate a signed game session.
                    if (len(episode.actions)<len(old_episode.actions) or
                        tuple(episode.receipts[:len(old_episode.receipts)])!=tuple(old_episode.receipts)):
                        raise ExpeditionSaveConflict("cannot rewind a committed game history")
                    generation=row["generation"]+1
                digest=sha256(payload).hexdigest()
                receipt=_receipt(run_id,generation,source,digest,prior)
                if row is None:
                    self._db.execute(
                        "INSERT INTO expedition_save VALUES(?,?,?,?,?,?,?)",
                        (run_id,generation,source,episode.traveler_digest,
                         payload,digest,receipt),
                    )
                else:
                    self._db.execute(
                        """UPDATE expedition_save SET generation=?,payload=?,
                        payload_sha256=?,receipt_digest=? WHERE run_id=?""",
                        (generation,payload,digest,receipt,run_id),
                    )
                self._db.execute(
                    "INSERT INTO expedition_save_history VALUES(?,?,?,?,?,?)",
                    (run_id,generation,source,digest,prior,receipt),
                )
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        return ExpeditionSave(run_id,generation,episode,digest,receipt)

    def history(self,run_id:str)->tuple[dict,...]:
        with self._lock:
            self._check(run_id)
            self._db.execute("BEGIN")
            try:
                row=self._db.execute(
                    "SELECT * FROM expedition_save WHERE run_id=?",(run_id,),
                ).fetchone()
                self._history(run_id,row)
                items=self._db.execute(
                    """SELECT generation,payload_sha256,previous_receipt,receipt_digest
                    FROM expedition_save_history WHERE run_id=? ORDER BY generation""",
                    (run_id,),
                ).fetchall()
                result=tuple(dict(x) for x in items)
                self._db.execute("COMMIT")
                return result
            except Exception:
                self._db.execute("ROLLBACK")
                raise

    def close(self):
        with self._lock:
            if not self._closed:
                self._db.close()
                self._closed=True

    def __enter__(self):
        self._check("healthcheck")
        return self

    def __exit__(self,*_):
        self.close()
