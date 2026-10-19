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
from .game_frontier_delta import (
    create_frame_delta, verify_frame_delta, FrameDeltaError,
)
from .game_frontier_native_chunks import inspect_native_chunks, compare_native_chunk_transitions, NativeChunkError


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
                CREATE TABLE IF NOT EXISTS frontier_deltas (
                    track TEXT NOT NULL, frame INTEGER NOT NULL,
                    content_digest TEXT NOT NULL,
                    PRIMARY KEY(track,frame),
                    FOREIGN KEY(content_digest) REFERENCES frontier_blobs(digest)
                );
                CREATE TABLE IF NOT EXISTS frontier_native_chunk_transitions (
                    track TEXT NOT NULL, frame INTEGER NOT NULL,
                    content_digest TEXT NOT NULL,
                    PRIMARY KEY(track,frame),
                    FOREIGN KEY(content_digest) REFERENCES frontier_blobs(digest)
                );
                CREATE TABLE IF NOT EXISTS frontier_native_chunk_evidence (
                    track TEXT NOT NULL, frame INTEGER NOT NULL,
                    content_digest TEXT NOT NULL,
                    PRIMARY KEY(track,frame),
                    FOREIGN KEY(content_digest) REFERENCES frontier_blobs(digest)
                );
                CREATE TABLE IF NOT EXISTS frontier_native_samples (
                    track TEXT NOT NULL, frame INTEGER NOT NULL,
                    content_digest TEXT NOT NULL,
                    PRIMARY KEY(track,frame),
                    FOREIGN KEY(content_digest) REFERENCES frontier_blobs(digest)
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

    def _validate_native_sample(self, frame: FrameReceipt, sample: Mapping) -> None:
        """Cross-check an untrusted Godot observation against stored actor state.

        This verifies consistency, never authenticates the origin of a
        client-supplied JSONL file as a trusted GPU observation.
        """
        if (not isinstance(sample,Mapping) or
            sample.get("schema")!="skeleton.game.native_physics_observation.v1" or
            sample.get("native_engine")!="godot4_physics" or
            sample.get("native_tick")!=frame.frame_index or
            sample.get("fps")!=frame.fps or
            sample.get("signed_gdd_digest")!=self.gdd.source_digest or
            type(sample.get("scene_candidate_digest")) is not str or
            len(sample["scene_candidate_digest"])!=64 or
            type(sample.get("ticks_usec")) is not int or
            sample["ticks_usec"]<0 or
            sample.get("authority")!="untrusted_native_candidate_observation_not_attested"):
            raise FrameJournalError("native observation schema/source rejected")
        native=sample.get("actors")
        observed={x.entity_id:x for c in frame.chunks for x in c.objects}
        if not isinstance(native,list) or len(native)!=len(observed) or not native:
            raise FrameJournalError("native sample must account for all source actors")
        names=set()
        for item in native:
            if not isinstance(item,Mapping) or item.get("id") not in observed:
                raise FrameJournalError("native observation unknown actor")
            name=item["id"]
            if name in names:
                raise FrameJournalError("native observation duplicate actor")
            names.add(name)
            if item.get("source_digest")!=observed[name].source_digest:
                raise FrameJournalError("native source asset hash mismatch")
            for key,expected in (
                ("world_xyz_m",observed[name].position),
                ("velocity_xyz_mps",observed[name].velocity),
            ):
                data=item.get(key)
                if (not isinstance(data,list) or len(data)!=3 or
                    any(type(x) not in (float,int) or not math.isfinite(x)
                        or abs(x)>1e8 for x in data)):
                    raise FrameJournalError("malformed native kinematic sample")
                if any(abs(float(x)-float(y))>1e-5 for x,y in
                       zip(data,(expected.x,expected.y,expected.z))):
                    raise FrameJournalError("native source disagrees with frame kinematics")

    def append(self, frame: FrameReceipt,
               evidence: Mapping | None = None, *,
               native_capture: Mapping | None = None,
               include_delta: bool = False) -> dict:
        """Commit only an independently verified next frame, atomically.

        If the same index is submitted twice, refuse; callers can load and
        compare if they need idempotent transport acknowledgement.
        """
        if not isinstance(frame,FrameReceipt) or type(include_delta) is not bool:
            raise FrameJournalError("typed source frame and delta selection required")
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
            delta_payload=None
            delta_hash=None
            if include_delta:
                delta_payload=create_frame_delta(
                    frame,self.gdd,previous=previous,
                    chunk_size_m=self.chunk_size_m,max_speed_mps=self.max_speed_mps)
                if not all(verify_frame_delta(
                    delta_payload,frame,self.gdd,previous=previous,
                    chunk_size_m=self.chunk_size_m,max_speed_mps=self.max_speed_mps)):
                    raise FrameJournalError("frame delta cannot reconstruct source")
                delta_hash=delta_payload["receipt_digest"]
            native_hash=None
            native_chunk_proof=None
            native_chunk_hash=None
            native_transition_proof=None
            native_transition_hash=None
            if native_capture is not None:
                self._validate_native_sample(frame,native_capture)
                native_chunk_proof=inspect_native_chunks(
                    native_capture,expected_chunk_size_m=self.chunk_size_m,
                    require_native_partition="native_chunks" in native_capture)
                native_chunk_hash=native_chunk_proof["receipt_digest"]
                prior_native=self.native_sample(head) if head>=0 else None
                native_transition_proof=compare_native_chunk_transitions(
                    native_capture,previous=prior_native,
                    expected_chunk_size_m=self.chunk_size_m,
                    max_speed_mps=self.max_speed_mps)
                native_transition_hash=native_transition_proof["receipt_digest"]
                native_hash=digest(native_capture)
            blobs=[
                (frame.receipt_digest,frame.payload()),
                (expected["receipt_digest"],expected),
            ]
            if native_hash is not None:
                blobs.append((native_hash,dict(native_capture)))
                blobs.append((native_chunk_hash,native_chunk_proof))
                blobs.append((native_transition_hash,native_transition_proof))
            if delta_hash is not None:
                blobs.append((delta_hash,delta_payload))
            for identity,payload in blobs:
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
            if delta_hash is not None:
                self._db.execute(
                    "INSERT INTO frontier_deltas(track,frame,content_digest) VALUES(?,?,?)",
                    (self.track,frame.frame_index,delta_hash))
            if native_hash is not None:
                self._db.execute(
                    "INSERT INTO frontier_native_samples(track,frame,content_digest) VALUES(?,?,?)",
                    (self.track,frame.frame_index,native_hash))
                self._db.execute(
                    "INSERT INTO frontier_native_chunk_evidence(track,frame,content_digest) VALUES(?,?,?)",
                    (self.track,frame.frame_index,native_chunk_hash))
                self._db.execute(
                    "INSERT INTO frontier_native_chunk_transitions(track,frame,content_digest) VALUES(?,?,?)",
                    (self.track,frame.frame_index,native_transition_hash))
            changed=self._db.execute(
                "UPDATE frontier_tracks SET head=?,fps=? WHERE name=? AND head=?",
                (frame.frame_index,frame.fps,self.track,head)).rowcount
            if changed!=1:
                raise FrameJournalError("concurrent journal head update")
            self._db.execute("COMMIT")
            return {"frame":frame.frame_index,
                    "frame_digest":frame.receipt_digest,
                    "chunk_evidence_digest":expected["receipt_digest"],
                    "native_capture_digest":native_hash,
                    "native_chunk_evidence_digest":native_chunk_hash,
                    "native_chunk_transition_digest":native_transition_hash,
                    "delta_digest":delta_hash,
                    "track":self.track,
                    "authority":"journal_committed_verified_candidate_only"}
        except Exception:
            self._db.execute("ROLLBACK")
            raise

    def advance(self, objects: tuple[FrameObject,...], *, fps: int = 60,
                notes: tuple[GDDFrameNote,...] = (),
                native_capture: Mapping | None = None,
                include_delta: bool = False) -> dict:
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
        return self.append(
            frame,native_capture=native_capture,include_delta=include_delta)

    def native_chunk_transitions(self, frame_index: int) -> dict | None:
        row=self._db.execute(
            "SELECT content_digest FROM frontier_native_chunk_transitions WHERE track=? AND frame=?",
            (self.track,frame_index)).fetchone()
        return self._blob(row[0]) if row else None

    def native_chunk_evidence(self, frame_index: int) -> dict | None:
        row=self._db.execute(
            "SELECT content_digest FROM frontier_native_chunk_evidence WHERE track=? AND frame=?",
            (self.track,frame_index)).fetchone()
        return self._blob(row[0]) if row else None

    def frame_delta(self, frame_index: int) -> dict | None:
        row=self._db.execute(
            "SELECT content_digest FROM frontier_deltas WHERE track=? AND frame=?",
            (self.track,frame_index)).fetchone()
        return self._blob(row[0]) if row else None

    def native_sample(self, frame_index: int) -> dict | None:
        row=self._db.execute(
            "SELECT content_digest FROM frontier_native_samples WHERE track=? AND frame=?",
            (self.track,frame_index)).fetchone()
        return self._blob(row[0]) if row else None

    def native_dynamics_evidence(self, frame_index: int) -> dict | None:
        """Independently replay body/contact data from a signed journal frame.

        Client-reported Godot observations are never hardware attestation.
        Legacy captures return None rather than claiming validated dynamics.
        """
        if type(frame_index) is not int or frame_index < 0:
            raise FrameJournalError("nonnegative dynamics frame required")
        native=self.native_sample(frame_index)
        if native is None:
            return None
        frame,_=self.load(frame_index)
        self._validate_native_sample(frame,native)
        proof=self.native_chunk_evidence(frame_index)
        if proof is None or proof != inspect_native_chunks(
            native,expected_chunk_size_m=self.chunk_size_m,
            require_native_partition="native_chunks" in native):
            raise FrameJournalError("native dynamics source evidence mismatch")
        from .game_frontier_native_dynamics import inspect_native_dynamics
        return inspect_native_dynamics(native)

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
            compact=self.frame_delta(index)
            if compact is not None and not all(verify_frame_delta(
                compact,frame,self.gdd,previous=previous,
                chunk_size_m=self.chunk_size_m,max_speed_mps=self.max_speed_mps)):
                raise FrameJournalError("content-addressed frame delta replay failed")
            native=self.native_sample(index)
            stored_native_chunks=self.native_chunk_evidence(index)
            stored_native_transition=self.native_chunk_transitions(index)
            if (native is None)!=(stored_native_chunks is None) or (
                native is None)!=(stored_native_transition is None):
                raise FrameJournalError("native chunk/source/transition attachment incomplete")
            if native is not None:
                self._validate_native_sample(frame,native)
                expected_native_chunks=inspect_native_chunks(
                    native,expected_chunk_size_m=self.chunk_size_m,
                    require_native_partition="native_chunks" in native)
                if stored_native_chunks!=expected_native_chunks:
                    raise FrameJournalError("native chunk evidence diverged from runtime source")
                previous_native=self.native_sample(index-1) if index else None
                expected_transition=compare_native_chunk_transitions(
                    native,previous=previous_native,
                    expected_chunk_size_m=self.chunk_size_m,
                    max_speed_mps=self.max_speed_mps)
                if stored_native_transition!=expected_transition:
                    raise FrameJournalError("native motion/chunk transition evidence altered")
                if index and self.native_sample(index-1) is not None and (
                    native["scene_candidate_digest"]!=
                    self.native_sample(index-1)["scene_candidate_digest"] or
                    native["ticks_usec"]<=self.native_sample(index-1)["ticks_usec"]
                ):
                    raise FrameJournalError("native candidate/timing discontinuity")
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
            self._db.execute(
                "INSERT INTO frontier_deltas(track,frame,content_digest) "
                "SELECT ?,frame,content_digest FROM frontier_deltas "
                "WHERE track=? AND frame<=?",
                (name,self.track,through))
            self._db.execute(
                "INSERT INTO frontier_native_chunk_transitions(track,frame,content_digest) "
                "SELECT ?,frame,content_digest FROM frontier_native_chunk_transitions "
                "WHERE track=? AND frame<=?",
                (name,self.track,through))
            self._db.execute(
                "INSERT INTO frontier_native_chunk_evidence(track,frame,content_digest) "
                "SELECT ?,frame,content_digest FROM frontier_native_chunk_evidence "
                "WHERE track=? AND frame<=?",
                (name,self.track,through))
            self._db.execute(
                "INSERT INTO frontier_native_samples(track,frame,content_digest) "
                "SELECT ?,frame,content_digest FROM frontier_native_samples "
                "WHERE track=? AND frame<=?",
                (name,self.track,through))
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise

    def evidence_page(
        self, *, start_frame: int = 0, limit: int = 128,
        actor_id: str | None = None,
        chunk_xy: tuple[int,int] | None = None,
        changes_only: bool = False,
    ) -> dict:
        """Browse bounded verified chunk/native evidence without raw frame dumps.

        Each listed frame is checked against its predecessor source; source
        hashes and GDD links are included for UI timeline navigation.
        Pagination uses a monotone source frame cursor, not query offsets.
        """
        if (type(start_frame) is not int or start_frame<0 or
            type(limit) is not int or not 1<=limit<=512 or
            type(changes_only) is not bool or
            actor_id is not None and (type(actor_id) is not str or
                not 1<=len(actor_id)<=128) or
            chunk_xy is not None and (
                not isinstance(chunk_xy,tuple) or len(chunk_xy)!=2 or
                any(type(x) is not int for x in chunk_xy))):
            raise FrameJournalError("bounded typed evidence query required")
        head,_=self._head()
        if start_frame>head+1:
            raise FrameJournalError("timeline cursor beyond current history")
        results=[]
        end=min(head+1,start_frame+limit)
        for index in range(start_frame,end):
            frame,proof=self.load(index)
            prior,prior_proof=(self.load(index-1) if index else (None,None))
            from .game_frontier_chunk_evidence import verify_frame_chunk_receipts
            if not all(verify_frame_chunk_receipts(
                proof,frame,self.gdd,previous=prior,
                previous_evidence=prior_proof,
                chunk_size_m=self.chunk_size_m,
                max_speed_mps=self.max_speed_mps)):
                raise FrameJournalError("timeline chunk source verification failed")
            referenced=[]
            movements=set()
            for chunk in proof["receipts"]:
                members=chunk["source_entities"]
                touched=(
                    chunk["arriving_entities"]+
                    chunk["departing_entities"]+
                    chunk["moved_within_chunk"])
                movements.update(touched)
                if ((actor_id is None or actor_id in members or
                     actor_id in touched) and
                    (chunk_xy is None or tuple(chunk["chunk_xy"])==chunk_xy)):
                    referenced.append(chunk["receipt_digest"])
            for retired in proof.get("retired_chunks",[]):
                names=[a["entity_id"] for a in retired["departing_entities"]]
                movements.update(names)
                if ((actor_id is None or actor_id in names) and
                    (chunk_xy is None or tuple(retired["chunk_xy"])==chunk_xy)):
                    referenced.append(retired["receipt_digest"])
            # Frame zero establishes source identity; it is not a movement
            # transition even though every actor is listed as an arrival.
            if index == 0:
                movements.clear()
            if not referenced or (changes_only and not movements):
                continue
            native=self.native_sample(index)
            native_proof=self.native_chunk_evidence(index)
            native_transition=self.native_chunk_transitions(index)
            if ((native is None)!=(native_proof is None) or
                (native is None)!=(native_transition is None)):
                raise FrameJournalError("native timeline evidence or transition incomplete")
            if native is not None:
                self._validate_native_sample(frame,native)
                if native_proof!=inspect_native_chunks(
                    native,expected_chunk_size_m=self.chunk_size_m,
                    require_native_partition="native_chunks" in native):
                    raise FrameJournalError("native timeline chunk source forged")
                expected_transition=compare_native_chunk_transitions(
                    native,previous=self.native_sample(index-1) if index else None,
                    expected_chunk_size_m=self.chunk_size_m,
                    max_speed_mps=self.max_speed_mps)
                if expected_transition!=native_transition:
                    raise FrameJournalError("native timeline transition source forged")
            dynamics=self.native_dynamics_evidence(index) if native else None
            dynamics_actors=(
                [row for row in dynamics["actors"]
                 if actor_id is None or row["id"]==actor_id]
                if dynamics else [])
            delta=self.frame_delta(index)
            result={
                "frame":index,"fps":frame.fps,
                "frame_digest":frame.receipt_digest,
                "signed_gdd_digest":self.gdd.source_digest,
                "chunk_receipts":referenced,
                "moved_actor_ids":sorted(movements),
                "migration_count":proof["cross_chunk_migrations"],
                "retired_chunk_count":proof.get("retired_chunk_count",0),
                "gdd_note_count":proof["source_note_count"],
                "chunk_evidence_digest":proof["receipt_digest"],
                "native_evidence_digest":(
                    native_proof["receipt_digest"] if native_proof else None),
                "native_transition_digest":(
                    native_transition["receipt_digest"] if native_transition else None),
                "native_dynamics_digest":(
                    dynamics["receipt_digest"] if dynamics else None),
                "native_reported_kinetic_energy_j":(
                    sum(row["kinetic_energy_j"] for row in dynamics_actors)
                    if dynamics else None),
                "native_resolved_actor_contact_count":(
                    sum(len(row["contact_actor_ids"]) for row in dynamics_actors)
                    if dynamics else None),
                "native_external_contact_count":(
                    sum(row["external_contact_count"] for row in dynamics_actors)
                    if dynamics else None),
                "native_contact_observation_count":(
                    sum(1 for actor in native_transition["actors"]
                        if type(actor["contact_count_after"]) is int and
                        actor["contact_count_after"]>0) if native_transition else None),
                "delta_digest":delta["receipt_digest"] if delta else None,
                "authority":"verified_source_evidence_cursor_not_native_gpu_proof",
            }
            results.append(result)
        output={
            "schema":"skeleton.game.chunk_evidence_timeline_page.v1",
            "track":self.track,
            "start_frame":start_frame,
            "through_frame":end-1,
            "next_frame":end if end<=head else None,
            "entries":results,
            "source_gdd_digest":self.gdd.source_digest,
            "filters":{"actor_id":actor_id,
                       "chunk_xy":list(chunk_xy) if chunk_xy else None,
                       "changes_only":changes_only},
        }
        output["receipt_digest"]=digest(output)
        return output

    def stats(self) -> dict:
        head,fps=self._head()
        blobs=self._db.execute("SELECT COUNT(*),SUM(LENGTH(content)) FROM frontier_blobs").fetchone()
        return {"track":self.track,"head":head,"fps":fps,
                "verified_frame_count":head+1,
                "deduplicated_blobs":blobs[0],
                "blob_utf8_text_bytes":blobs[1] or 0,
                "source_gdd_digest":self.gdd.source_digest}
