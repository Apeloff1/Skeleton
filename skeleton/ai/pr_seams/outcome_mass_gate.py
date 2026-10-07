"""Governed project-outcome mass gate into candidate training

Plane: outcome_mass_gate
PR: https://github.com/Apeloff1/Skeleton/pull/3480
Branch: automation/governed-project-learning-20261007
Law: stored_prose=0. Pointer citations only. No network. No torch.
Parent cite: #80 and #3480.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Mapping, Sequence

LAW = "stored_prose=0"
CITATION = "https://github.com/Apeloff1/Skeleton/pull/3480"
KIND = "outcome-mass"


def _canon(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _h(prefix: str, payload: object) -> str:
    return prefix + sha256(_canon(payload).encode("utf-8")).hexdigest()


def _id(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    if "\n" in value or len(value) > 240:
        raise ValueError(f"{name} must be a pointer clause")
    return value.strip()


def _u(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative int")
    return value


def card(hit: bool, **extra: object) -> dict:
    body = {
        "kind": KIND,
        "hit": bool(hit),
        "law": LAW,
        "citation": CITATION,
        "stored_prose": 0,
    }
    body.update(extra)
    if body["stored_prose"] != 0:
        raise PermissionError("stored prose is forbidden")
    return body

@dataclass(frozen=True)
class Outcome:
    outcome_id: str
    project_id: str
    succeeded: bool
    mass: int
    prior_mass: int
    evidence_id: str

    @classmethod
    def create(cls, project_id, succeeded, mass, prior_mass, evidence_id):
        _id(project_id, "project_id")
        if not isinstance(succeeded, bool):
            raise ValueError("succeeded must be bool")
        _u(mass, "mass")
        _u(prior_mass, "prior_mass")
        _id(evidence_id, "evidence_id")
        payload = {
            "project_id": project_id,
            "succeeded": succeeded,
            "mass": mass,
            "prior_mass": prior_mass,
            "evidence_id": evidence_id,
        }
        return cls(_h("outcome-sha256:", payload), project_id, succeeded, mass, prior_mass, evidence_id)


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    outcome_id: str
    admitted: bool
    reason: str
    clipped_mass: int


def admit(outcome: Outcome) -> Candidate:
    if not outcome.succeeded:
        reason = "not-succeeded"
        admitted = False
        clipped = outcome.prior_mass
    elif outcome.prior_mass == 0:
        reason = "no-prior"
        admitted = False
        clipped = 0
    else:
        ceiling = (outcome.prior_mass * 11) // 10
        if outcome.mass > ceiling:
            reason = "mass-snowball"
            admitted = False
            clipped = ceiling
        else:
            reason = "admit"
            admitted = True
            clipped = outcome.mass
    payload = {
        "outcome_id": outcome.outcome_id,
        "admitted": admitted,
        "reason": reason,
        "clipped_mass": clipped,
    }
    return Candidate(_h("cand-sha256:", payload), outcome.outcome_id, admitted, reason, clipped)


def exit_card(outcome: Outcome, candidate: Candidate) -> dict:
    return card(
        candidate.admitted,
        candidate_id=candidate.candidate_id,
        reason=candidate.reason,
        mass=candidate.clipped_mass,
        mass_hint=outcome.mass,
        succeeded=outcome.succeeded,
    )
