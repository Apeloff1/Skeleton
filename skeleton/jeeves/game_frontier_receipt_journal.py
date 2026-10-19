"""Durable, transactional and replay-verifiable game-frame receipt journal.

This is a single-writer logical journal with SQLite atomic commits and
content-addressed payload deduplication. It persists the existing verified
FrameReceipt and chunk evidence, not a new game-state authority. Branches
preserve history; rollback creates a fork rather than deleting evidence.

The host must supply a validated signed GDD and canonical runtime-observed
FrameObjects. No network, OS positioning, model weights or invented GPU
attestations are involved.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import sqlite3
from typing import Iterator, Mapping

from .game_frontier_production import Vec3
from .game_frontier_frame_coherence import (
    FrameChunk, FrameCoherenceError, FrameObject, FrameReceipt, GDDFrameNote,
    GDDSource, advance_frame, digest, verify_frame,
)
from .game_frontier_chunk_evidence import (
    ChunkEvidenceError, build_frame_chunk_receipts, verify_frame_chunk_receipts,
)


class FrameJournalError(ValueError):
    pass


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def _identity(value: str) -> str:
    if (type(value) is not str or not 1 <= len(value) <= 128 or
        not all(c.isalnum() or c in "-_." for c in value) or
        value in (".", "..")):
        raise FrameJournalError("bounded literal journal/branch ID required")
    return value


def _decode_frame(payload: Mapping, expected_digest: str) -> FrameReceipt:
    """Deserialize only the defined frame schema, never arbitrary model code."""
    try:
        chunks = tuple(
            FrameChunk(
                int(part["payload"]["frame"]),
                tuple(part["payload"]["cell"]),
                tuple(FrameObject(
                    src["id"], Vec3(*src["position"]),
                    Vec3(*src["velocity"]), src["source"])
                    for src in part["payload"]["entities"]),
                part["digest"])
            for part in payload["chunks"])
        notes = tuple(GDDFrameNote(
            note["world_law_index"], note["category"], note["text"],
            note["author_kind"]) for note in payload["notes"])
        frame = FrameReceipt(
            payload["frame"], payload["clock_ns"], payload["fps"],
            payload["gdd_digest"], payload["prior"],
            chunks, notes, payload["a"], payload["b"], payload["verified"],
            expected_digest, payload["authority"])
        if digest(frame.payload()) != expected_digest:
            raise FrameJournalError("serialized frame has inconsistent identity")
        return frame
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
        raise FrameJournalError("invalid journal frame schema") from exc


class FrameReceiptJournal:
    """Crash-safe source receipt journal; one canonical writer per track.

    SQLite serializes append/fork transactions using BEGIN IMMEDIATE.
    No record is overwritten; content is shared by SHA-256 across forks.
    """

    def __init__(self, database_path: str | Path, gdd: GDDSource, *,
                 track: str = "production", chunk_size_m: float = 32.,
                 max_speed_mps: float = 500.) -> None:
        self.path = Path(database_path)
        if (not isinstance(gdd, GDDSource) or
            gdd.authority != "signed_story_bible_read_only"):
            raise FrameJournalError("canonical verified GDD required")
        self.gdd = gdd
        self.track = _identity(track)
        if (type(chunk_size_m) not in (int,float) or
            not math.isfinite(chunk_size_m) or
            not .1 <= chunk_size_m <= 1e5 or
            type(max_speed_mps) not in (int,float) or
            not math.isfinite(max_speed_mps) or
            not 0 < max_speed_mps <= 1e5):
            raise FrameJournalError("explicit bounded verifier configuration required")
        self.chunk_size_m = float(chunk_size_m)
        self.max_speed_mps = float(max_speed_mps)
        if not self.path.parent.is_dir() or self.path.is_symlink():
            raise FrameJournalError("journal parent must exist and not be a symlink file")
        self._db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        try:
            self._db.execute("PRAGMA foreign_keys=ON")
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS frontier_blobs (
                    digest TEXT PRIMARY KEY, content TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS frontier_tracks (
                    name TEXT PRIMARY KEY, project TEXT NOT NULL,
                    gdd_digest TEXT NOT NULL, chunk_size REAL NOT NULL,
                    max_speed REAL NOT NULL, fps INTEGER,
                    head INTEGER NOT NULL DEFAULT -1
                );
                CREATE TABLE IF NOT EXISTS frontier_commits (
                    track TEXT NOT NULL, frame INTEGER NOT NULL,
                    frame_digest TEXT NOT NULL, evidence_digest TEXT NOT NULL,
                    previous_frame_digest TEXT,
                    PRIMARY KEY(track,frame),
                    FOREIGN KEY(track) REFERENCES frontier_tracks(name),
                    FOREIGN KEY(frame_digest) REFERENCES frontier_blobs(digest),
                    FOREIGN KEY(evidence_digest) REFERENCES frontier_blobs(digest)
                );
            """)
            self._db.execute("BEGIN IMMEDIATE")
            try:
                row = self._db.execute(
                    "SELECT project,gdd_digest,chunk_size,max_speed FROM frontier_tracks WHERE name=?",
                    (self.track,)).fetchone()
                if row is None:
                    self._db.execute(
                        "INSERT INTO frontier_tracks(name,project,gdd_digest,chunk_size,max_speed) VALUES(?,?,?,?,?)",
                        (self.track,gdd.project_id,gdd.source_digest,
                         self.chunk_size_m,self.max_speed_mps))
                elif (row[0]!=gdd.project_id or row[1]!=gdd.source_digest or
                      row[2]!=self.chunk_size_m or row[3]!=self.max_speed_mps):
                    raise FrameJournalError("existing journal track does not match GDD/verifier contract")
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        except Exception:
            self._db.close()
            raise

    def __enter__(self) -> "FrameReceiptJournal":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self._db.close()

    def _head(self) -> tuple[int,int | None]:
        row=self._db.execute(
            "SELECT head,fps FROM frontier_tracks WHERE name=?",
            (self.track,)).fetchone()
        if row is None:
            raise FrameJournalError("missing journal track")
        return row[0],row[1]

    def _blob(self, identity: str) -> dict:
        row=self._db.execute(
            "SELECT content FROM frontier_blobs WHERE digest=?",
            (identity,)).fetchone()
        if row is None:
            raise FrameJournalError("content-addressed receipt blob missing")
        try:
            data=json.loads(row[0])
        except (ValueError,TypeError) as exc:
            raise FrameJournalError("corrupt receipt JSON") from exc
        content = ({k:v for k,v in data.items() if k!="receipt_digest"}
                   if "receipt_digest" in data else data)
        if digest(content)!=identity:
            raise FrameJournalError("content-addressed blob failed hash authentication")
        return data

    def load(self, frame_index: int) -> tuple[FrameReceipt,dict]:
        if type(frame_index) is not int or frame_index<0:
            raise FrameJournalError("nonnegative frame index required")
        row=self._db.execute(
            "SELECT frame_digest,evidence_digest,previous_frame_digest FROM frontier_commits "
            "WHERE track=? AND frame=?", (self.track,frame_index)).fetchone()
        if row is None:
            raise FrameJournalError("requested frame not committed")
        actual=_decode_frame(self._blob(row[0]),row[0])
        proof=self._blob(row[1])
        if (actual.frame_index!=frame_index or
            actual.previous_digest!=row[2] or
            proof.get("source_frame_digest")!=row[0] or
            proof.get("receipt_digest")!=row[1]):
            raise FrameJournalError("frame evidence or predecessor index conflict")
        return actual,proof

    def append(self, frame: FrameReceipt,
               evidence: Mapping | None = None) -> dict:
        """Commit only an independently verified next frame, atomically.

        If the same index is submitted twice, refuse; callers can load and
        compare if they need idempotent transport acknowledgement.
        """
        if not isinstance(frame,FrameReceipt):
            raise FrameJournalError("typed source FrameReceipt required")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            head,fps=self._head()
            if frame.frame_index!=head+1 or (
                fps is not None and fps!=frame.fps):
                raise FrameJournalError("missing or inconsistent journal frame/FPS")
            previous,old_evidence=(self.load(head) if head>=0 else (None,None))
            a,b=verify_frame(frame,self.gdd,previous=previous,
                             chunk_size_m=self.chunk_size_m,
                             max_speed_mps=self.max_speed_mps)
            if not a or not b:
                raise FrameJournalError("both source frame verifiers must pass")
            expected=build_frame_chunk_receipts(
                frame,self.gdd,previous=previous,
                previous_evidence=old_evidence,
                chunk_size_m=self.chunk_size_m,max_speed_mps=self.max_speed_mps)
            if evidence is not None and evidence!=expected:
                raise FrameJournalError("provided chunk evidence differs from recomputed source")
            if not all(verify_frame_chunk_receipts(
                expected,frame,self.gdd,previous=previous,
                previous_evidence=old_evidence,
                chunk_size_m=self.chunk_size_m,
                max_speed_mps=self.max_speed_mps)):
                raise FrameJournalError("chunk evidence has not passed independent replay")
            for identity,payload in (
                (frame.receipt_digest,frame.payload()),
                (expected["receipt_digest"],expected),
            ):
                bare = ({k:v for k,v in payload.items() if k!="receipt_digest"}
                        if "receipt_digest" in payload else payload)
                if digest(bare)!=identity:
                    raise FrameJournalError("unverified source blob")
                self._db.execute(
                    "INSERT OR IGNORE INTO frontier_blobs(digest,content) VALUES(?,?)",
                    (identity,_canonical(payload)))
                if self._blob(identity)!=payload:
                    raise FrameJournalError("CAS content mismatch on existing identity")
            self._db.execute(
                "INSERT INTO frontier_commits(track,frame,frame_digest,evidence_digest,previous_frame_digest) "
                "VALUES(?,?,?,?,?)",
                (self.track,frame.frame_index,frame.receipt_digest,
                 expected["receipt_digest"],frame.previous_digest))
            changed=self._db.execute(
                "UPDATE frontier_tracks SET head=?,fps=? WHERE name=? AND head=?",
                (frame.frame_index,frame.fps,self.track,head)).rowcount
            if changed!=1:
                raise FrameJournalError("concurrent journal head update")
            self._db.execute("COMMIT")
            return {"frame":frame.frame_index,
                    "frame_digest":frame.receipt_digest,
                    "chunk_evidence_digest":expected["receipt_digest"],
                    "track":self.track,
                    "authority":"journal_committed_verified_candidate_only"}
        except Exception:
            self._db.execute("ROLLBACK")
            raise

    def advance(self, objects: tuple[FrameObject,...], *, fps: int = 60,
                notes: tuple[GDDFrameNote,...] = ()) -> dict:
        """Produce source frame from host-observed actor samples and commit."""
        head,saved_fps=self._head()
        previous=self.load(head)[0] if head>=0 else None
        if saved_fps is not None and fps != saved_fps:
            raise FrameJournalError("journal presentation FPS cannot drift mid-track")
        try:
            frame=advance_frame(
                frame_index=head+1,fps=saved_fps or fps,
                gdd=self.gdd,objects=objects,previous=previous,notes=notes,
                chunk_size_m=self.chunk_size_m,max_speed_mps=self.max_speed_mps)
        except (FrameCoherenceError, ValueError) as exc:
            raise FrameJournalError("source frame failed canonical temporal/GDD verification") from exc
        return self.append(frame)

    def replay(self, *, through: int | None = None) -> dict:
        """Replay the entire retained prefix, fail closed at first corruption."""
        head,_=self._head()
        last=head if through is None else through
        if type(last) is not int or last < -1 or last>head:
            raise FrameJournalError("replay range outside committed journal")
        previous=None
        old_evidence=None
        for index in range(last+1):
            frame,proof=self.load(index)
            a,b=verify_frame(frame,self.gdd,previous=previous,
                             chunk_size_m=self.chunk_size_m,
                             max_speed_mps=self.max_speed_mps)
            e1,e2=verify_frame_chunk_receipts(
                proof,frame,self.gdd,previous=previous,
                previous_evidence=old_evidence,
                chunk_size_m=self.chunk_size_m,
                max_speed_mps=self.max_speed_mps)
            if not(a and b and e1 and e2):
                raise FrameJournalError(f"replay verification failed at frame {index}")
            previous,old_evidence=frame,proof
        return {"track":self.track,"verified_frames":last+1,
                "head_frame_digest":previous.receipt_digest if previous else None,
                "head_evidence_digest":(
                    old_evidence["receipt_digest"] if old_evidence else None),
                "signed_gdd_digest":self.gdd.source_digest,
                "authority":"replayed_source_receipts_not_native_runtime_proof"}

    def fork(self, new_track: str, *, through: int) -> None:
        """Non-destructive rollback: fork a verified prefix, preserving history.

        Objects are CAS-deduplicated. Another caller may append on the new
        branch only by opening the new track explicitly.
        """
        name=_identity(new_track)
        if name==self.track:
            raise FrameJournalError("rollback must name a distinct branch")
        head,fps=self._head()
        if type(through) is not int or not 0<=through<=head:
            raise FrameJournalError("rollback requires committed checkpoint")
        self.replay(through=through)
        self._db.execute("BEGIN IMMEDIATE")
        try:
            self._db.execute(
                "INSERT INTO frontier_tracks(name,project,gdd_digest,chunk_size,max_speed,fps,head) "
                "VALUES(?,?,?,?,?,?,?)",
                (name,self.gdd.project_id,self.gdd.source_digest,
                 self.chunk_size_m,self.max_speed_mps,fps,through))
            self._db.execute(
                "INSERT INTO frontier_commits(track,frame,frame_digest,evidence_digest,previous_frame_digest) "
                "SELECT ?,frame,frame_digest,evidence_digest,previous_frame_digest "
                "FROM frontier_commits WHERE track=? AND frame<=? ORDER BY frame",
                (name,self.track,through))
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise

    def stats(self) -> dict:
        head,fps=self._head()
        blobs=self._db.execute("SELECT COUNT(*),SUM(LENGTH(content)) FROM frontier_blobs").fetchone()
        return {"track":self.track,"head":head,"fps":fps,
                "verified_frame_count":head+1,
                "deduplicated_blobs":blobs[0],
                "blob_utf8_text_bytes":blobs[1] or 0,
                "source_gdd_digest":self.gdd.source_digest}
