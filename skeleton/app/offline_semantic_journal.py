"""Transactional derived ANN generation custody in the existing local chat DB.

The journal owns no source bytes, approvals or model identity. A generation is
only active if the existing source authority still matches its recorded snapshot.
Completed generations are immutable. Interrupted jobs are never auto-published.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import secrets
import sqlite3
import time

from skeleton.retrieval.disk_semantic_ann import DiskANN,DiskANNPolicy,_private_root
from skeleton.retrieval.learned_embeddings import _pin
from skeleton.ai.model_runtime.runtime_contracts import RuntimeContractError


@dataclass(frozen=True,slots=True)
class GenerationRecord:
    generation:str
    manifest_sha256:str
    source_snapshot:str
    feature_space:str
    revision:int


class SemanticIndexJournal:
    def __init__(self,library,root):
        from .offline_knowledge import OfflineKnowledgeLibrary
        if not isinstance(library,OfflineKnowledgeLibrary) or library._semantic_ranker is None:
            raise TypeError("canonical learned reference library required")
        self.library=library
        self.root=_private_root(root)
        # Root binding prevents reinterpreting a prior active generation under
        # another directory; source model scope remains canonical.
        self.scope=sha256(("offline-semantic-journal:"+library.model_digest+":"+
            library.tokenizer_digest+":"+str(self.root)).encode()).hexdigest()
        self.db=library.store._db
        self.lock=library.store._lock
        with self.lock:
            self.db.execute("""CREATE TABLE IF NOT EXISTS offline_semantic_generations (
              scope TEXT NOT NULL,generation TEXT NOT NULL,
              base_revision INTEGER NOT NULL,status TEXT NOT NULL,
              source_snapshot TEXT NOT NULL,feature_space TEXT NOT NULL,
              manifest_sha256 TEXT,created_ns INTEGER NOT NULL,
              finished_ns INTEGER,
              PRIMARY KEY(scope,generation))""")
            self.db.execute("""CREATE TABLE IF NOT EXISTS offline_semantic_active (
              scope TEXT PRIMARY KEY,generation TEXT NOT NULL,
              revision INTEGER NOT NULL,manifest_sha256 TEXT NOT NULL,
              source_snapshot TEXT NOT NULL,feature_space TEXT NOT NULL)""")

    def _current(self):
        row=self.db.execute("""SELECT generation,manifest_sha256,source_snapshot,feature_space,revision
          FROM offline_semantic_active WHERE scope=?""",(self.scope,)).fetchone()
        if row is None:return None
        if not isinstance(row[0],str) or not row[0].startswith("gen-") or len(row[0])!=36 or any(c not in "0123456789abcdef" for c in row[0][4:]) or not all(_pin(x) for x in row[1:4]) or type(row[4]) is not int or row[4]<1:
            raise RuntimeContractError("semantic generation journal record malformed")
        return GenerationRecord(*row)

    def current(self):
        with self.lock:return self._current()

    def _open(self,active):
        if active.feature_space!=self.library._semantic_ranker.identity:
            raise RuntimeContractError("active semantic feature space differs from local ranker")
        return DiskANN(self.root/active.generation,active.manifest_sha256,
            expected_space=active.feature_space,expected_snapshot=active.source_snapshot)

    def attach(self):
        with self.lock:
            active=self._current()
            if active is None:raise RuntimeContractError("no active semantic generation")
            if active.source_snapshot!=self.library.semantic_source_snapshot():
                raise RuntimeContractError("active semantic generation stale")
            index=self._open(active)
            if index.dimension!=self.library._semantic_ranker.encoder.policy.dimension:
                raise RuntimeContractError("active semantic index geometry mismatch")
            self.library._semantic_ann=index
            self.library._semantic_journal=self
            return active

    def _fail(self,name,status):
        with self.lock:
            self.db.execute("""UPDATE offline_semantic_generations SET status=?,finished_ns=?
                WHERE scope=? AND generation=? AND status='building'""",(status,time.time_ns(),self.scope,name))

    def refresh(self,policy,*,interrupt=None):
        """Build a candidate; publish by source-snapshot and active-revision CAS.

        Multiple independent processes may build concurrently, but only the
        winner of the DB transaction can become current. A crash before
        publication leaves an inactive generation, not a guessed active pin.
        """
        if not isinstance(policy,DiskANNPolicy):raise TypeError("explicit ANN resource policy required")
        ranker=self.library._semantic_ranker
        name="gen-"+secrets.token_hex(16)
        with self.lock:
            if self.db.in_transaction:raise RuntimeContractError("semantic journal requires independent transaction")
            self.db.execute("BEGIN IMMEDIATE")
            try:
                prior=self._current()
                snapshot=self.library.semantic_source_snapshot()
                rev=prior.revision if prior else 0
                self.db.execute("""INSERT INTO offline_semantic_generations
                    VALUES(?,?,?,'building',?,?,NULL,?,NULL)""",
                    (self.scope,name,rev,snapshot,ranker.identity,time.time_ns()))
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK");raise
        try:
            previous=self._open(prior) if prior is not None and prior.feature_space==ranker.identity else None
            receipt=self.library.build_semantic_ann(self.root,name,policy,previous=previous,interrupt=interrupt)
            candidate=DiskANN(receipt["path"],receipt["manifest_sha256"],expected_space=ranker.identity,expected_snapshot=snapshot)
            if candidate.dimension!=ranker.encoder.policy.dimension:raise RuntimeContractError("candidate semantic geometry mismatch")
            with self.lock:
                self.db.execute("BEGIN IMMEDIATE")
                try:
                    current=self._current()
                    if current!=prior or self.library.semantic_source_snapshot()!=snapshot:
                        raise RuntimeContractError("semantic publication CAS lost or source snapshot changed")
                    if self.db.execute("""UPDATE offline_semantic_generations
                        SET status='active',manifest_sha256=?,finished_ns=?
                        WHERE scope=? AND generation=? AND status='building'""",
                        (candidate.manifest_sha256,time.time_ns(),self.scope,name)).rowcount!=1:
                        raise RuntimeContractError("candidate semantic journal was fenced")
                    if prior:
                        self.db.execute("""UPDATE offline_semantic_generations SET status='historical'
                            WHERE scope=? AND generation=? AND status='active'""",(self.scope,prior.generation))
                    self.db.execute("""INSERT INTO offline_semantic_active VALUES(?,?,?,?,?,?)
                        ON CONFLICT(scope) DO UPDATE SET generation=excluded.generation,
                        revision=excluded.revision,manifest_sha256=excluded.manifest_sha256,
                        source_snapshot=excluded.source_snapshot,feature_space=excluded.feature_space""",
                        (self.scope,name,rev+1,candidate.manifest_sha256,snapshot,ranker.identity))
                    self.db.execute("COMMIT")
                except BaseException:
                    self.db.execute("ROLLBACK");raise
                self.library._semantic_ann=candidate
                self.library._semantic_journal=self
            return {**receipt,"source_snapshot":snapshot,"generation":name,"active_revision":rev+1,
                    "status":"active_derived_index_not_source_authority"}
        except BaseException:
            self._fail(name,"failed")
            raise

    def refresh_attachment(self):
        """Observe an explicitly published generation from another local process."""
        active=self.current()
        current=self.library._semantic_ann
        if active is None:raise RuntimeContractError("semantic active generation unavailable")
        if current is None or current.manifest_sha256!=active.manifest_sha256:
            self.attach()
        elif self.library.semantic_source_snapshot()!=active.source_snapshot:
            raise RuntimeContractError("active semantic generation stale")

    def history(self,*,limit=50):
        if type(limit) is not int or not 1<=limit<=256:raise ValueError("bounded semantic generation history required")
        with self.lock:
            rows=self.db.execute("""SELECT generation,status,source_snapshot,feature_space,manifest_sha256,
                base_revision,created_ns,finished_ns FROM offline_semantic_generations
                WHERE scope=? ORDER BY created_ns DESC,generation LIMIT ?""",(self.scope,limit)).fetchall()
        keys=("generation","status","source_snapshot","feature_space","manifest_sha256",
              "base_revision","created_ns","finished_ns")
        return [dict(zip(keys,row)) for row in rows]

    def fence_abandoned(self,generation,*,expected_base_revision):
        """Explicit operator recovery only; never delete files or activate a job.

        A live builder fenced by this operation must fail its publication CAS.
        """
        if not isinstance(generation,str) or not generation.startswith("gen-") or len(generation)!=36 or any(c not in "0123456789abcdef" for c in generation[4:]) or type(expected_base_revision) is not int or expected_base_revision<0:
            raise ValueError("explicit abandoned generation identity required")
        with self.lock:
            row=self.db.execute("""UPDATE offline_semantic_generations SET status='abandoned',finished_ns=?
                 WHERE scope=? AND generation=? AND base_revision=? AND status='building'""",
                 (time.time_ns(),self.scope,generation,expected_base_revision))
            if row.rowcount!=1:raise RuntimeContractError("semantic recovery compare-and-swap failed")
