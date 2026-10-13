"""Durable model-release evidence handoff for shadow-trained candidates.

The canonical model-serving plane remains the owner of weight admission,
publication, rollback and activation. This journal records exact proposal,
operator-approval, external admission and rollback evidence. It never invokes
model loading or claims a model is active from an internal decision alone.

Every terminal transition requires an application-supplied independent verifier
with an external receipt, explicit verifier identity and exact proposal digest.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Any, Callable, Sequence

from .flgb_training_runtime import require_digest, require_id, digest_json
from .shadow_candidate_gate import CandidateReleaseProposal
from .promotion_lifecycle import RuntimeAdmission, RollbackProof


class ReleaseJournalError(ValueError):
    """Failed model-release handoff, authority or evidence chain."""


class ReleaseState(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    ACTIVE_EXTERNAL = "active_external"
    ROLLED_BACK_EXTERNAL = "rolled_back_external"
    REJECTED = "rejected"
    QUARANTINED = "quarantined"


def _digest(value: Any) -> str:
    try:
        encoded = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("utf-8")
    except (ValueError, TypeError) as exc:
        raise ReleaseJournalError("release journal requires deterministic JSON") from exc
    return sha256(encoded).hexdigest()


def _identity(value: str, label: str) -> str:
    try:
        return require_id(value, label)
    except Exception as exc:
        raise ReleaseJournalError(f"invalid {label}") from exc


def _sha(value: str, label: str) -> str:
    try:
        return require_digest(value, label)
    except Exception as exc:
        raise ReleaseJournalError(f"invalid {label}") from exc


@dataclass(frozen=True, slots=True)
class ExternalReleaseReceipt:
    proposal_digest: str
    state: ReleaseState
    actor_id: str
    verifier_id: str
    at_ns: int
    external_evidence_digest: str
    runtime_model_digest: str
    rollback_checkpoint_digest: str

    def __post_init__(self) -> None:
        for name in ("proposal_digest", "external_evidence_digest",
                     "runtime_model_digest", "rollback_checkpoint_digest"):
            _sha(getattr(self, name), name)
        _identity(self.actor_id, "actor_id")
        _identity(self.verifier_id, "verifier_id")
        if self.actor_id == self.verifier_id:
            raise ReleaseJournalError("external release proof cannot be self-verified")
        if not isinstance(self.state, ReleaseState) or self.state is ReleaseState.PROPOSED:
            raise ReleaseJournalError("external receipt requires transition state")
        if type(self.at_ns) is not int or self.at_ns < 0:
            raise ReleaseJournalError("external release event time must be non-negative")

    @property
    def digest(self) -> str:
        return _digest({
            "schema": "skeleton.external_release_receipt.v1",
            "proposal_digest": self.proposal_digest,
            "state": self.state.value,
            "actor_id": self.actor_id, "verifier_id": self.verifier_id,
            "at_ns": self.at_ns,
            "external_evidence_digest": self.external_evidence_digest,
            "runtime_model_digest": self.runtime_model_digest,
            "rollback_checkpoint_digest": self.rollback_checkpoint_digest,
        })


@dataclass(frozen=True, slots=True)
class ReleaseStatus:
    proposal_digest: str
    intake_id: str
    state: ReleaseState
    version: int
    event_digest: str
    external_evidence_digest: str | None
    verified_by: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_digest": self.proposal_digest,
            "intake_id": self.intake_id,
            "state": self.state.value,
            "version": self.version,
            "event_digest": self.event_digest,
            "external_evidence_digest": self.external_evidence_digest,
            "verified_by": self.verified_by,
        }


_SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS model_release_proposals (
    proposal_digest TEXT PRIMARY KEY,
    intake_id TEXT NOT NULL,
    proposal_json TEXT NOT NULL,
    state TEXT NOT NULL,
    version INTEGER NOT NULL,
    last_event_digest TEXT NOT NULL,
    external_evidence_digest TEXT,
    verifier_id TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS model_release_intake
    ON model_release_proposals(intake_id);
CREATE TABLE IF NOT EXISTS model_release_admissions (
    proposal_digest TEXT PRIMARY KEY,
    admission_digest TEXT NOT NULL,
    authority_id TEXT NOT NULL,
    checkpoint_digest TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_release_events (
    sequence INTEGER PRIMARY KEY,
    proposal_digest TEXT NOT NULL,
    prior_event_digest TEXT NOT NULL,
    event_digest TEXT NOT NULL UNIQUE,
    event_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_release_meta (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    head TEXT NOT NULL,
    event_count INTEGER NOT NULL
);
"""
GENESIS = "0" * 64


class ModelReleaseJournal:
    """Persistent model release evidence custodian; host performs all actual effects."""

    def __init__(
        self, path: str | Path, *,
        verify_external: Callable[[CandidateReleaseProposal, ExternalReleaseReceipt], bool],
    ) -> None:
        self.path = Path(path)
        if not self.path.is_absolute():
            raise ReleaseJournalError("host model-release database path must be absolute")
        if not callable(verify_external):
            raise ReleaseJournalError("external model-serving proof verifier required")
        self._verify_external = verify_external
        self._lock = RLock()
        self._db = sqlite3.connect(
            str(self.path), isolation_level=None, timeout=10,
            check_same_thread=False,
        )
        try:
            self._db.execute("PRAGMA busy_timeout=10000")
            self._db.executescript(_SCHEMA)
            self._db.execute(
                "INSERT OR IGNORE INTO model_release_meta VALUES(1, ?, 0)",
                (GENESIS,),
            )
        except BaseException:
            self._db.close()
            raise

    @staticmethod
    def _proposal(row: str) -> CandidateReleaseProposal:
        try:
            obj = json.loads(row)
            if not isinstance(obj, dict) or obj.pop("schema", None) != "skeleton.candidate_release_proposal.v1":
                raise ValueError("schema mismatch")
            for key in ("dispatch_performed", "production_weights_changed", "requires"):
                obj.pop(key, None)
            return CandidateReleaseProposal(**obj)
        except (ValueError, TypeError) as exc:
            raise ReleaseJournalError("persisted release proposal is invalid") from exc

    def _append_event(
        self, *, proposal: CandidateReleaseProposal, state: ReleaseState,
        version: int, receipt_digest: str,
        at_ns: int,
    ) -> str:
        meta = self._db.execute(
            "SELECT head,event_count FROM model_release_meta WHERE singleton=1"
        ).fetchone()
        if meta is None:
            raise ReleaseJournalError("release journal head missing")
        prior, number = meta
        if number >= 200_000:
            raise ReleaseJournalError("model release journal capacity exceeded")
        event = {
            "schema": "skeleton.model_release_event.v1",
            "sequence": number,
            "prior_event_digest": prior,
            "proposal_digest": proposal.digest,
            "state": state.value, "version": version,
            "receipt_digest": receipt_digest, "at_ns": at_ns,
        }
        event_digest = _digest(event)
        self._db.execute(
            "INSERT INTO model_release_events VALUES (?,?,?,?,?)",
            (number, proposal.digest, prior, event_digest,
             json.dumps(event, sort_keys=True, separators=(",", ":"),
                        ensure_ascii=True, allow_nan=False)),
        )
        self._db.execute(
            "UPDATE model_release_meta SET head=?,event_count=? WHERE singleton=1",
            (event_digest, number + 1),
        )
        return event_digest

    def propose(self, proposal: CandidateReleaseProposal, *,
                actor_id: str, at_ns: int) -> ReleaseStatus:
        if not isinstance(proposal, CandidateReleaseProposal):
            raise ReleaseJournalError("release requires a typed shadow candidate proposal")
        _identity(actor_id, "actor_id")
        if type(at_ns) is not int or at_ns < 0:
            raise ReleaseJournalError("host proposal timestamp invalid")
        if len(json.dumps(proposal.as_dict()).encode("utf-8")) > 32 * 1024:
            raise ReleaseJournalError("candidate release proposal exceeds size limit")
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                if self._db.execute(
                    "SELECT 1 FROM model_release_proposals WHERE "
                    "proposal_digest=? OR intake_id=?",
                    (proposal.digest, proposal.intake_id),
                ).fetchone():
                    raise ReleaseJournalError("candidate release already staged")
                event = self._append_event(
                    proposal=proposal, state=ReleaseState.PROPOSED, version=0,
                    receipt_digest=_digest({"proposer": actor_id}),
                    at_ns=at_ns,
                )
                self._db.execute(
                    "INSERT INTO model_release_proposals VALUES (?,?,?,?,?,?,?,?)",
                    (proposal.digest, proposal.intake_id,
                     json.dumps(proposal.as_dict(), sort_keys=True,
                                separators=(",", ":"), ensure_ascii=True),
                     ReleaseState.PROPOSED.value, 0, event, None, None),
                )
                self._db.execute("COMMIT")
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
            return ReleaseStatus(
                proposal.digest, proposal.intake_id, ReleaseState.PROPOSED,
                0, event, None, None,
            )

    def transition(
        self, proposal_digest: str, receipt: ExternalReleaseReceipt, *,
        expected_version: int,
        runtime_admission: RuntimeAdmission | None = None,
        rollback_proof: RollbackProof | None = None,
    ) -> ReleaseStatus:
        _sha(proposal_digest, "proposal_digest")
        if type(expected_version) is not int or expected_version < 0:
            raise ReleaseJournalError("expected release version invalid")
        if not isinstance(receipt, ExternalReleaseReceipt):
            raise ReleaseJournalError("typed external release proof required")
        if receipt.proposal_digest != proposal_digest:
            raise ReleaseJournalError("external receipt refers to different candidate")
        with self._lock:
            try:
                self._db.execute("BEGIN IMMEDIATE")
                row = self._db.execute(
                    "SELECT proposal_json,state,version FROM model_release_proposals "
                    "WHERE proposal_digest=?",
                    (proposal_digest,),
                ).fetchone()
                if row is None or row[2] != expected_version:
                    raise ReleaseJournalError("release proposal missing or stale")
                proposal = self._proposal(row[0])
                prior = ReleaseState(row[1])
                allowed = {
                    ReleaseState.PROPOSED: {
                        ReleaseState.APPROVED, ReleaseState.REJECTED,
                        ReleaseState.QUARANTINED,
                    },
                    ReleaseState.APPROVED: {
                        ReleaseState.ACTIVE_EXTERNAL, ReleaseState.REJECTED,
                        ReleaseState.QUARANTINED,
                    },
                    ReleaseState.ACTIVE_EXTERNAL: {
                        ReleaseState.ROLLED_BACK_EXTERNAL,
                        ReleaseState.QUARANTINED,
                    },
                    ReleaseState.QUARANTINED: {ReleaseState.REJECTED},
                    ReleaseState.REJECTED: set(),
                    ReleaseState.ROLLED_BACK_EXTERNAL: set(),
                }
                if receipt.state not in allowed[prior]:
                    raise ReleaseJournalError("illegal model-release state transition")
                if receipt.runtime_model_digest != (
                    proposal.weights_digest if receipt.state is ReleaseState.ACTIVE_EXTERNAL
                    else proposal.champion_digest if receipt.state is ReleaseState.ROLLED_BACK_EXTERNAL
                    else proposal.champion_digest
                ):
                    raise ReleaseJournalError("model-serving receipt has mismatched weights")
                if receipt.rollback_checkpoint_digest != proposal.rollback_checkpoint_digest:
                    raise ReleaseJournalError("release receipt changes rollback identity")
                if receipt.verifier_id in {proposal.verifier_id}:
                    raise ReleaseJournalError("release operator verifier must differ from candidate evaluator")
                if receipt.state is ReleaseState.ACTIVE_EXTERNAL:
                    if not isinstance(runtime_admission, RuntimeAdmission):
                        raise ReleaseJournalError("runtime admission proof required")
                    if (runtime_admission.candidate_digest != proposal.candidate_digest
                            or runtime_admission.prior_model_digest != proposal.champion_digest
                            or runtime_admission.admitted_model_digest != proposal.weights_digest
                            or runtime_admission.checkpoint_digest != proposal.rollback_checkpoint_digest):
                        raise ReleaseJournalError("runtime admission does not match release identity")
                if receipt.state is ReleaseState.ROLLED_BACK_EXTERNAL:
                    prior_admission = self._db.execute(
                        "SELECT admission_digest,authority_id,checkpoint_digest "
                        "FROM model_release_admissions WHERE proposal_digest=?",
                        (proposal_digest,),
                    ).fetchone()
                    if prior_admission is None:
                        raise ReleaseJournalError("rollback lacks bound runtime admission")
                    if not isinstance(rollback_proof, RollbackProof):
                        raise ReleaseJournalError("verified external rollback proof required")
                    if (rollback_proof.restored_model_digest != proposal.champion_digest
                            or rollback_proof.checkpoint_digest != proposal.rollback_checkpoint_digest
                            or not rollback_proof.executed or not rollback_proof.verified
                            or rollback_proof.admission_digest != prior_admission[0]
                            or rollback_proof.checkpoint_digest != prior_admission[2]
                            or rollback_proof.verifier_id in (
                                receipt.verifier_id, prior_admission[1], proposal.verifier_id,
                            )):
                        raise ReleaseJournalError("model was not proven independently restored to champion")
                if self._verify_external(proposal, receipt) is not True:
                    raise ReleaseJournalError("independent model-serving owner rejected external proof")
                if receipt.state is ReleaseState.ACTIVE_EXTERNAL:
                    if runtime_admission.admission_authority in (
                        proposal.verifier_id, receipt.verifier_id,
                    ):
                        raise ReleaseJournalError("model admission needs independent operator")
                    self._db.execute(
                        "INSERT INTO model_release_admissions VALUES (?,?,?,?)",
                        (proposal_digest, runtime_admission.digest,
                         runtime_admission.admission_authority,
                         runtime_admission.checkpoint_digest),
                    )
                version = expected_version + 1
                event = self._append_event(
                    proposal=proposal, state=receipt.state,
                    version=version, receipt_digest=receipt.digest,
                    at_ns=receipt.at_ns,
                )
                self._db.execute(
                    "UPDATE model_release_proposals SET state=?,version=?,"
                    "last_event_digest=?,external_evidence_digest=?,verifier_id=? "
                    "WHERE proposal_digest=? AND version=?",
                    (receipt.state.value, version, event, receipt.external_evidence_digest,
                     receipt.verifier_id, proposal_digest, expected_version),
                )
                self._db.execute("COMMIT")
            except BaseException:
                if self._db.in_transaction:
                    self._db.execute("ROLLBACK")
                raise
            return ReleaseStatus(
                proposal_digest, proposal.intake_id, receipt.state,
                version, event, receipt.external_evidence_digest,
                receipt.verifier_id,
            )

    def list_status(self, *, limit: int = 100,
                    state: ReleaseState | None = None) -> tuple[ReleaseStatus, ...]:
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ReleaseJournalError("release list limit outside 1..1000")
        if state is not None and not isinstance(state, ReleaseState):
            raise ReleaseJournalError("release state filter invalid")
        where = "" if state is None else " WHERE state=?"
        args = [] if state is None else [state.value]
        with self._lock:
            rows = self._db.execute(
                "SELECT proposal_digest,intake_id,state,version,last_event_digest,"
                "external_evidence_digest,verifier_id "
                "FROM model_release_proposals" + where +
                " ORDER BY intake_id LIMIT ?",
                args + [limit],
            )
            return tuple(ReleaseStatus(
                p, i, ReleaseState(s), v, e, x, verifier
            ) for p, i, s, v, e, x, verifier in rows)

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def __enter__(self) -> "ModelReleaseJournal":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


__all__ = [
    "ReleaseJournalError", "ReleaseState", "ExternalReleaseReceipt",
    "ReleaseStatus", "ModelReleaseJournal",
]
