"""Hypothesis registry for falsifiable gameplay mechanics analysis.

Records predicted outcomes and disconfirming conditions before trials.
The registry separates speculation, tested findings and rejected claims.
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import sqlite3


class HypothesisState(str, Enum):
    PROPOSED = "proposed"
    TESTING = "testing"
    SUPPORTED = "supported"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class MechanicHypothesis:
    hypothesis_id: str
    mechanic: str
    statement: str
    predicted_observation: str
    falsifying_observation: str
    source_fingerprint: str


@dataclass(frozen=True)
class HypothesisResult:
    hypothesis_id: str
    state: HypothesisState
    trial_digest: str
    notes: str


class DragonHypothesisRegistry:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        db.execute("""
            CREATE TABLE IF NOT EXISTS dragon_hypotheses(
                owner TEXT NOT NULL,id TEXT NOT NULL,mechanic TEXT NOT NULL,
                statement TEXT NOT NULL,predicted TEXT NOT NULL,
                falsifying TEXT NOT NULL,source_fingerprint TEXT NOT NULL,
                PRIMARY KEY(owner,id))
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS dragon_hypothesis_results(
                owner TEXT NOT NULL,id TEXT NOT NULL,state TEXT NOT NULL,
                trial_digest TEXT NOT NULL,notes TEXT NOT NULL,
                PRIMARY KEY(owner,id))
        """)
        db.commit()

    def propose(self, owner: str, hypothesis: MechanicHypothesis, *,
                authorized: bool) -> None:
        if not authorized:
            raise PermissionError("hypothesis proposal requires authorization")
        for value in (
            hypothesis.hypothesis_id, hypothesis.mechanic,
            hypothesis.statement, hypothesis.predicted_observation,
            hypothesis.falsifying_observation,
        ):
            if not isinstance(value, str) or not 1 <= len(value) <= 1000:
                raise ValueError("invalid hypothesis field")
        if len(hypothesis.source_fingerprint) != 64 or any(
            c not in "0123456789abcdef" for c in hypothesis.source_fingerprint
        ):
            raise ValueError("invalid hypothesis source fingerprint")
        current = self.db.execute("""
            SELECT mechanic,statement,predicted,falsifying,source_fingerprint
            FROM dragon_hypotheses WHERE owner=? AND id=?
        """, (owner, hypothesis.hypothesis_id)).fetchone()
        expected = (
            hypothesis.mechanic, hypothesis.statement,
            hypothesis.predicted_observation, hypothesis.falsifying_observation,
            hypothesis.source_fingerprint,
        )
        if current:
            if current != expected:
                raise ValueError("hypothesis identity conflict")
            return
        with self.db:
            self.db.execute("""
                INSERT INTO dragon_hypotheses VALUES(?,?,?,?,?,?,?)
            """, (owner, hypothesis.hypothesis_id, *expected))

    def resolve(self, owner: str, result: HypothesisResult, *,
                authorized: bool) -> None:
        if not authorized:
            raise PermissionError("hypothesis resolution requires authorization")
        if result.state not in (
            HypothesisState.SUPPORTED, HypothesisState.REFUTED,
            HypothesisState.INCONCLUSIVE,
        ):
            raise ValueError("hypothesis result must be terminal")
        if not isinstance(result.trial_digest, str) or len(result.trial_digest) != 64 or any(
            c not in "0123456789abcdef" for c in result.trial_digest
        ):
            raise ValueError("invalid trial digest")
        if not isinstance(result.notes, str) or len(result.notes) > 2000:
            raise ValueError("invalid trial notes")
        with self.db:
            if not self.db.execute("""
                SELECT 1 FROM dragon_hypotheses WHERE owner=? AND id=?
            """, (owner, result.hypothesis_id)).fetchone():
                raise ValueError("hypothesis not registered")
            existing = self.db.execute("""
                SELECT state,trial_digest,notes FROM dragon_hypothesis_results
                WHERE owner=? AND id=?
            """, (owner, result.hypothesis_id)).fetchone()
            expected = (result.state.value, result.trial_digest, result.notes)
            if existing:
                if existing != expected:
                    raise ValueError("immutable hypothesis result conflict")
                return
            self.db.execute("""
                INSERT INTO dragon_hypothesis_results VALUES(?,?,?,?,?)
            """, (owner, result.hypothesis_id, *expected))

    def resolve_from_falsification(self, owner: str, outcome, *,
                                   authorized: bool) -> HypothesisResult:
        """Persist a terminal state derived from executable falsification evidence."""
        if not authorized:
            raise PermissionError("hypothesis resolution requires authorization")
        # Local import avoids making the registry depend on worker construction.
        from .dragon_causal_falsification_worker import FalsificationOutcome
        if not isinstance(outcome, FalsificationOutcome):
            raise TypeError("falsification outcome required")
        states = {
            "supported": HypothesisState.SUPPORTED,
            "refuted": HypothesisState.REFUTED,
            "inconclusive": HypothesisState.INCONCLUSIVE,
        }
        if outcome.verdict not in states:
            raise ValueError("unknown falsification verdict")
        result = HypothesisResult(
            outcome.hypothesis_id, states[outcome.verdict],
            outcome.trial_evidence_digest,
            "Derived from preregistered causal-falsification evidence.",
        )
        self.resolve(owner, result, authorized=True)
        return result

    def erase(self, owner: str, *, authorized: bool) -> int:
        if not authorized:
            raise PermissionError("hypothesis erasure requires authorization")
        with self.db:
            self.db.execute(
                "DELETE FROM dragon_hypothesis_results WHERE owner=?", (owner,),
            )
            return self.db.execute(
                "DELETE FROM dragon_hypotheses WHERE owner=?", (owner,),
            ).rowcount
