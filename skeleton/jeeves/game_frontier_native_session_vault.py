"""Durable production-style vault for native game session checkpoints.

SQLite FULL/WAL transactional append, externally cold-verified snapshots,
immutable receipt-chain indexes, idempotent replay, bounded compaction, and
fresh source-journal validation on restart. Keeps the game's authored GDD
read-only. Durability is subject to host/filesystem guarantees; this is not
proof of running unattended for months or providing OS process supervision.
"""
from __future__ import annotations
import json
from pathlib import Path
import re
import sqlite3

from .game_frontier_native_quest_session import NativeQuestSessionError,_sha
from .game_frontier_native_quest_audit import audit_native_quest_checkpoint


_SESSION_ID=re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")


class NativeSessionVaultError(ValueError):
    pass


class NativeSessionVault:
    """One authored quest-session slot. Every append has a cold replay proof."""

    def __init__(self, path: str | Path, *, session_id: str) -> None:
        self.path=Path(path)
        if (type(session_id) is not str or _SESSION_ID.fullmatch(session_id) is None
            or not self.path.parent.is_dir() or self.path.is_symlink()):
            raise NativeSessionVaultError("safe existing game vault parent and session identity required")
        self.session_id=session_id
        self._db=sqlite3.connect(str(self.path),timeout=20,isolation_level=None)
        try:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS game_native_quest_vault(
                  session_id TEXT NOT NULL,
                  serial INTEGER NOT NULL,
                  frame INTEGER NOT NULL,
                  previous_root TEXT,
                  checkpoint_digest TEXT NOT NULL,
                  cold_audit_digest TEXT NOT NULL,
                  signed_gdd_digest TEXT NOT NULL,
                  scene_candidate_digest TEXT NOT NULL,
                  approved_manifest_digest TEXT NOT NULL,
                  authored_pages_digest TEXT NOT NULL,
                  quest_graph_digest TEXT NOT NULL,
                  actor_id TEXT NOT NULL,
                  track TEXT NOT NULL,
                  snapshot_json TEXT,
                  receipt_digest TEXT NOT NULL,
                  PRIMARY KEY (session_id,serial),
                  UNIQUE (session_id,frame)
                );
            """)
        except BaseException:
            self._db.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.close()

    def close(self):
        self._db.close()

    @staticmethod
    def _signed_row(row: dict) -> dict:
        keys=("session_id","serial","frame","previous_root",
              "checkpoint_digest","cold_audit_digest","signed_gdd_digest",
              "scene_candidate_digest","approved_manifest_digest",
              "authored_pages_digest","quest_graph_digest","actor_id","track")
        return {key:row[key] for key in keys}

    def _rows(self) -> list[dict]:
        columns=("session_id","serial","frame","previous_root",
                 "checkpoint_digest","cold_audit_digest","signed_gdd_digest",
                 "scene_candidate_digest","approved_manifest_digest",
                 "authored_pages_digest","quest_graph_digest","actor_id","track",
                 "snapshot_json","receipt_digest")
        rows=self._db.execute(
            "SELECT "+",".join(columns)+" FROM game_native_quest_vault "
            "WHERE session_id=? ORDER BY serial",(self.session_id,)).fetchall()
        result=[dict(zip(columns,row)) for row in rows]
        previous_root=None
        previous_frame=-1
        for index,item in enumerate(result):
            if (item["serial"]!=index or
                item["previous_root"]!=previous_root or
                type(item["frame"]) is not int or item["frame"]<=previous_frame or
                item["receipt_digest"]!=_sha(self._signed_row(item))):
                raise NativeSessionVaultError(
                    "vault receipt chain, ordering or source identity corrupted")
            previous_root=item["receipt_digest"]
            previous_frame=item["frame"]
        return result

    def append(self,checkpoint: dict,journal,pages,quest_graph,approvals, *,
               actor_id: str,scene_candidate_digest: str,
               inject_crash_before_commit: bool = False) -> dict:
        """Atomic save after replay; faults roll back without rewriting slots."""
        if (type(checkpoint) is not dict or
            checkpoint.get("session_id")!=self.session_id or
            type(inject_crash_before_commit) is not bool):
            raise NativeSessionVaultError("session checkpoint/identity mismatch")
        audit=audit_native_quest_checkpoint(
            journal,pages,quest_graph,approvals,checkpoint,
            actor_id=actor_id,scene_candidate_digest=scene_candidate_digest)
        self._db.execute("BEGIN IMMEDIATE")
        try:
            rows=self._rows()
            prior=rows[-1] if rows else None
            if prior is not None and checkpoint["frame"]==prior["frame"]:
                if (checkpoint["receipt_digest"]!=prior["checkpoint_digest"]
                    or audit["receipt_digest"]!=prior["cold_audit_digest"]):
                    raise NativeSessionVaultError(
                        "same-frame replay cannot mutate a committed checkpoint")
                self._db.execute("COMMIT")
                return {"reused_existing":True,"receipt_digest":prior["receipt_digest"],
                        "frame":prior["frame"],"serial":prior["serial"]}
            if prior is not None and checkpoint["frame"]<prior["frame"]:
                raise NativeSessionVaultError("game save cannot roll back existing receipt chain")
            proof={
                "session_id":self.session_id,
                "serial":len(rows),
                "frame":checkpoint["frame"],
                "previous_root":prior["receipt_digest"] if prior else None,
                "checkpoint_digest":checkpoint["receipt_digest"],
                "cold_audit_digest":audit["receipt_digest"],
                "signed_gdd_digest":journal.gdd.source_digest,
                "scene_candidate_digest":scene_candidate_digest,
                "approved_manifest_digest":approvals["receipt_digest"],
                "authored_pages_digest":checkpoint["authored_pages_digest"],
                "quest_graph_digest":checkpoint["quest_graph_digest"],
                "actor_id":actor_id,"track":journal.track,
            }
            if prior is not None and (
                prior["signed_gdd_digest"]!=proof["signed_gdd_digest"]
                or prior["scene_candidate_digest"]!=proof["scene_candidate_digest"]
                or prior["actor_id"]!=proof["actor_id"] or
                prior["track"]!=proof["track"] or
                prior["authored_pages_digest"]!=proof["authored_pages_digest"] or
                prior["quest_graph_digest"]!=proof["quest_graph_digest"]):
                raise NativeSessionVaultError("one local save chain cannot change game canon")
            root=_sha(proof)
            self._db.execute(
                "INSERT INTO game_native_quest_vault VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (*[proof[key] for key in (
                    "session_id","serial","frame","previous_root",
                    "checkpoint_digest","cold_audit_digest","signed_gdd_digest",
                    "scene_candidate_digest","approved_manifest_digest",
                    "authored_pages_digest","quest_graph_digest","actor_id","track")],
                 json.dumps(checkpoint,sort_keys=True,separators=(",",":"),
                            allow_nan=False),root))
            if inject_crash_before_commit:
                raise NativeSessionVaultError("injected write interruption before COMMIT")
            self._db.execute("COMMIT")
            return {"reused_existing":False,"receipt_digest":root,
                    "frame":checkpoint["frame"],"serial":proof["serial"]}
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def recover(self,journal,pages,quest_graph,approvals, *,
                actor_id: str,scene_candidate_digest: str) -> dict:
        """Verify receipt ancestry and replay latest retained save from frame 0."""
        rows=self._rows()
        if not rows or rows[-1]["snapshot_json"] is None:
            raise NativeSessionVaultError("no recoverable game state retained")
        final=rows[-1]
        if (final["signed_gdd_digest"]!=journal.gdd.source_digest or
            final["scene_candidate_digest"]!=scene_candidate_digest or
            final["actor_id"]!=actor_id or final["track"]!=journal.track or
            final["approved_manifest_digest"]!=approvals["receipt_digest"]):
            raise NativeSessionVaultError("wrong authored game, actor, track or approvals")
        try:
            checkpoint=json.loads(final["snapshot_json"])
        except (ValueError,TypeError) as exc:
            raise NativeSessionVaultError("stored game snapshot corrupted") from exc
        if (checkpoint.get("receipt_digest")!=final["checkpoint_digest"]
            or checkpoint.get("authored_pages_digest")!=final["authored_pages_digest"]
            or checkpoint.get("quest_graph_digest")!=final["quest_graph_digest"]):
            raise NativeSessionVaultError("stored checkpoint differs from immutable vault receipt")
        new_audit=audit_native_quest_checkpoint(
            journal,pages,quest_graph,approvals,checkpoint,
            actor_id=actor_id,scene_candidate_digest=scene_candidate_digest)
        if new_audit["receipt_digest"]!=final["cold_audit_digest"]:
            raise NativeSessionVaultError("source game cold audit no longer matches restored save")
        return {
            "schema":"skeleton.game.native_quest_vault_recovery.v1",
            "session_id":self.session_id,
            "serial":final["serial"],
            "frame":final["frame"],
            "vault_receipt_digest":final["receipt_digest"],
            "independent_cold_audit_digest":new_audit["receipt_digest"],
            "retained_receipt_count":len(rows),
            "compacted_snapshot_count":sum(row["snapshot_json"] is None for row in rows),
            "checkpoint":checkpoint,
            "authority":"verified_local_game_save_recovery_not_canonical_GDD_writer",
        }

    def rotate(self,*,keep_latest: int = 2) -> dict:
        """Prune *payloads only*: all immutable ancestry receipts are retained."""
        if type(keep_latest) is not int or not 1<=keep_latest<=1024:
            raise NativeSessionVaultError("bounded retained save window required")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            rows=self._rows()
            before=sum(x["snapshot_json"] is not None for x in rows)
            retire={x["serial"] for x in rows[:-keep_latest]}
            for sequence in retire:
                self._db.execute(
                    "UPDATE game_native_quest_vault SET snapshot_json=NULL "
                    "WHERE session_id=? AND serial=?", (self.session_id,sequence))
            self._db.execute("COMMIT")
            return {
                "session_id":self.session_id,
                "retained_snapshots":min(len(rows),keep_latest),
                "archived_receipts":len(rows),
                "retired_snapshots_this_rotation":(
                    before-min(before,keep_latest)),
                "head_receipt_digest":rows[-1]["receipt_digest"] if rows else None,
            }
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
