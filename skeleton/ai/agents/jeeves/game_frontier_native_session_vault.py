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

    def inspect_storage_integrity(self) -> dict:
        """Run SQLite's real page/link integrity check, beyond SHA row ancestry.

        A valid SQLite file does NOT imply trusted RPG actions: callers must
        also cold-replay source receipts. Refuse non-WAL or weakened sync.
        """
        check=self._db.execute("PRAGMA quick_check").fetchall()
        if check!=[("ok",)]:
            raise NativeSessionVaultError("SQLite native game save integrity check failed")
        mode=self._db.execute("PRAGMA journal_mode").fetchone()[0]
        sync=self._db.execute("PRAGMA synchronous").fetchone()[0]
        if mode.lower()!="wal" or sync!=2:
            raise NativeSessionVaultError("durable game vault requires SQLite WAL and FULL sync")
        page_count=self._db.execute("PRAGMA page_count").fetchone()[0]
        free_pages=self._db.execute("PRAGMA freelist_count").fetchone()[0]
        if not 0<=free_pages<=page_count:
            raise NativeSessionVaultError("SQLite page accounting is invalid")
        return {
            "schema":"skeleton.game.native_vault_sqlite_health.v1",
            "session_id":self.session_id,
            "sqlite_check":"ok","journal_mode":"wal",
            "synchronous":"full",
            "page_count":page_count,
            "free_page_count":free_pages,
            "authority":"sqlite_page_integrity_not_authenticated_gameplay",
        }

    def recover(self,journal,pages,quest_graph,approvals, *,
                actor_id: str,scene_candidate_digest: str) -> dict:
        """Verify receipt ancestry and replay latest retained save from frame 0."""
        self.inspect_storage_integrity()
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

    def audit_retained_history(
        self,journal,pages,quest_graph,approvals, *,
        actor_id: str,scene_candidate_digest: str,
    ) -> dict:
        """Independently cold-replay ALL retained game snapshots.

        Receipt ancestry remains verifiable after rotation. Missing compacted
        payloads are reported explicitly, never treated as replayed evidence.
        This is costly by design and runs at recovery/qualification boundaries.
        """
        self.inspect_storage_integrity()
        rows=self._rows()
        if not rows or rows[-1]["snapshot_json"] is None:
            raise NativeSessionVaultError("auditable game head checkpoint required")
        counts=0
        last=-1
        verified=[]
        for row in rows:
            if (row["signed_gdd_digest"]!=journal.gdd.source_digest or
                row["scene_candidate_digest"]!=scene_candidate_digest or
                row["actor_id"]!=actor_id or row["track"]!=journal.track or
                row["approved_manifest_digest"]!=approvals["receipt_digest"]):
                raise NativeSessionVaultError("historical receipt bound to different game source")
            if row["snapshot_json"] is None:
                counts+=1
                continue
            try:
                saved=json.loads(row["snapshot_json"])
            except (TypeError,ValueError) as exc:
                raise NativeSessionVaultError("retained game snapshot is invalid JSON") from exc
            if (saved.get("receipt_digest")!=row["checkpoint_digest"] or
                saved.get("frame")!=row["frame"] or
                saved.get("authored_pages_digest")!=row["authored_pages_digest"] or
                saved.get("quest_graph_digest")!=row["quest_graph_digest"]):
                raise NativeSessionVaultError("retained snapshot contradicts its archived receipt")
            proven=audit_native_quest_checkpoint(
                journal,pages,quest_graph,approvals,saved,
                actor_id=actor_id,scene_candidate_digest=scene_candidate_digest)
            if proven["receipt_digest"]!=row["cold_audit_digest"]:
                raise NativeSessionVaultError("retained snapshot differs from original frame history")
            verified.append({
                "frame":row["frame"],"serial":row["serial"],
                "checkpoint_digest":saved["receipt_digest"],
                "vault_receipt_digest":row["receipt_digest"],
            })
            last=row["frame"]
        report={
            "schema":"skeleton.game.native_vault_history_audit.v1",
            "session_id":self.session_id,"source_gdd_digest":journal.gdd.source_digest,
            "scene_candidate_digest":scene_candidate_digest,
            "ancestry_receipts_verified":len(rows),
            "retained_snapshots_cold_replayed":len(verified),
            "compacted_payloads_not_replayable":counts,
            "last_cold_replayed_frame":last,
            "head_receipt_digest":rows[-1]["receipt_digest"],
            "retained_snapshots":verified,
            "authority":"archived_receipt_ancestry_and_retained_cold_replay_not_long_term_attestation",
        }
        report["receipt_digest"]=_sha(report)
        return report


    def export_recovery_manifest(
        self,journal,pages,quest_graph,approvals, *,
        actor_id: str,scene_candidate_digest: str,
    ) -> dict:
        """Externally reviewable, data-only save receipt with no game writes.

        No secret/private key is in scope: SHA binds the manifest bytes, not
        operator identity. Verify independently against journal and vault.
        """
        source=self.recover(
            journal,pages,quest_graph,approvals,actor_id=actor_id,
            scene_candidate_digest=scene_candidate_digest)
        audit=self.audit_retained_history(
            journal,pages,quest_graph,approvals,actor_id=actor_id,
            scene_candidate_digest=scene_candidate_digest)
        storage=self.inspect_storage_integrity()
        manifest={
            "schema":"skeleton.game.native_vault_external_recovery.v1",
            "session_id":self.session_id,"actor_id":actor_id,
            "track":journal.track,"signed_gdd_digest":journal.gdd.source_digest,
            "scene_candidate_digest":scene_candidate_digest,
            "latest_verified_frame":source["frame"],
            "checkpoint_digest":source["checkpoint"]["receipt_digest"],
            "vault_head_receipt_digest":source["vault_receipt_digest"],
            "source_history_audit_digest":audit["receipt_digest"],
            "source_cold_audit_digest":source["independent_cold_audit_digest"],
            "retained_receipts":audit["ancestry_receipts_verified"],
            "retained_snapshots_replayed":audit["retained_snapshots_cold_replayed"],
            "compacted_payloads_not_replayable":audit["compacted_payloads_not_replayable"],
            "sqlite_health":storage,
            "authority":"externally_replayable_local_game_save_proof_not_user_authentication",
        }
        manifest["receipt_digest"]=_sha(manifest)
        return manifest

    def verify_external_recovery_manifest(
        self,journal,pages,quest_graph,approvals,recorded: object, *,
        actor_id: str,scene_candidate_digest: str,
    ) -> bool:
        """Require exact independently reconstructed save proof."""
        expected=self.export_recovery_manifest(
            journal,pages,quest_graph,approvals,actor_id=actor_id,
            scene_candidate_digest=scene_candidate_digest)
        if type(recorded) is not dict or recorded!=expected:
            raise NativeSessionVaultError("external recovery proof diverges from actual game journal")
        return True


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
