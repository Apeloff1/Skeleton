"""Independent gold-master release arbitration for the AI game builder."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .contracts import canonical_digest


class ReleaseArbitrationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FamilyQualification:
    family_id: str
    passed: bool
    evidence_digest: str

    def __post_init__(self) -> None:
        if self.family_id not in {f"GB{i:02d}" for i in range(1, 51)}:
            raise ValueError("family_id must be GB01..GB50")
        if len(self.evidence_digest) < 16:
            raise ValueError("family evidence digest must be stable")


@dataclass(frozen=True, slots=True)
class GoldMasterBundle:
    artifact_digest: str
    build_digest: str
    canon_digest: str
    provenance_digest: str
    replay_digest: str
    rollback_target_digest: str
    red_team_digest: str
    family_qualifications: tuple[FamilyQualification, ...]
    critical_gate_digests: tuple[tuple[str, str], ...]

    @classmethod
    def create(
        cls,
        *,
        artifact_digest: str,
        build_digest: str,
        canon_digest: str,
        provenance_digest: str,
        replay_digest: str,
        rollback_target_digest: str,
        red_team_digest: str,
        family_qualifications: Iterable[FamilyQualification],
        critical_gate_digests: Mapping[str, str],
    ) -> "GoldMasterBundle":
        for value in (
            artifact_digest,
            build_digest,
            canon_digest,
            provenance_digest,
            replay_digest,
            rollback_target_digest,
            red_team_digest,
        ):
            if not isinstance(value, str) or len(value) < 16:
                raise ValueError("gold-master identities must be stable digests")
        families = tuple(sorted(family_qualifications, key=lambda row: row.family_id))
        if [row.family_id for row in families] != [f"GB{i:02d}" for i in range(1, 51)]:
            raise ValueError("gold-master bundle requires exactly GB01..GB50")
        gates = tuple(sorted((str(k), str(v)) for k, v in critical_gate_digests.items()))
        if not gates or any(not key or len(value) < 16 for key, value in gates):
            raise ValueError("critical gates require stable evidence digests")
        return cls(
            artifact_digest=artifact_digest,
            build_digest=build_digest,
            canon_digest=canon_digest,
            provenance_digest=provenance_digest,
            replay_digest=replay_digest,
            rollback_target_digest=rollback_target_digest,
            red_team_digest=red_team_digest,
            family_qualifications=families,
            critical_gate_digests=gates,
        )

    @property
    def eligible(self) -> bool:
        return all(row.passed for row in self.family_qualifications)

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "artifact_digest": self.artifact_digest,
                "build_digest": self.build_digest,
                "canon_digest": self.canon_digest,
                "critical_gate_digests": dict(self.critical_gate_digests),
                "family_qualifications": [
                    {
                        "evidence_digest": row.evidence_digest,
                        "family_id": row.family_id,
                        "passed": row.passed,
                    }
                    for row in self.family_qualifications
                ],
                "provenance_digest": self.provenance_digest,
                "red_team_digest": self.red_team_digest,
                "replay_digest": self.replay_digest,
                "rollback_target_digest": self.rollback_target_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class TribunalVote:
    authority_id: str
    bundle_digest: str
    accept: bool
    evidence_digest: str
    rationale_digest: str

    def __post_init__(self) -> None:
        if not self.authority_id.strip():
            raise ValueError("authority_id must be non-empty")
        for value in (self.bundle_digest, self.evidence_digest, self.rationale_digest):
            if len(value) < 16:
                raise ValueError("tribunal vote identities must be stable digests")


@dataclass(frozen=True, slots=True)
class GoldMasterVerdict:
    bundle_digest: str
    accepted: bool
    authority_ids: tuple[str, ...]
    vote_digests: tuple[str, ...]
    verdict_digest: str


class GoldMasterTribunal:
    """Terminal authority distinct from creative rivals and routine evaluators."""

    def __init__(
        self,
        authority_ids: Iterable[str],
        *,
        quorum: int = 3,
        forbidden_ids: Iterable[str] = ("rival_a", "rival_b"),
    ) -> None:
        ids = tuple(str(x).strip() for x in authority_ids)
        forbidden = set(forbidden_ids)
        if len(ids) != len(set(ids)) or any(not x for x in ids):
            raise ValueError("gold-master authority identities must be unique")
        if any(x in forbidden for x in ids):
            raise ValueError("creative/routine forbidden authority cannot join tribunal")
        if quorum < 3 or quorum > len(ids):
            raise ValueError("gold-master quorum must be >=3 and <= authority count")
        self.authority_ids = ids
        self.quorum = quorum
        self._votes: dict[tuple[str, str], TribunalVote] = {}

    def vote(self, vote: TribunalVote) -> None:
        if vote.authority_id not in self.authority_ids:
            raise ReleaseArbitrationError("vote authority is not a tribunal member")
        key = (vote.bundle_digest, vote.authority_id)
        if key in self._votes:
            raise ReleaseArbitrationError("duplicate tribunal vote")
        self._votes[key] = vote

    def decide(self, bundle: GoldMasterBundle) -> GoldMasterVerdict:
        if not bundle.eligible:
            raise ReleaseArbitrationError("gold-master bundle has failed family qualification")
        votes = tuple(
            self._votes[(bundle.digest, authority)]
            for authority in self.authority_ids
            if (bundle.digest, authority) in self._votes
        )
        if len(votes) < self.quorum:
            raise ReleaseArbitrationError("gold-master tribunal quorum is not satisfied")
        # Terminal release is conservative: quorum is necessary but any dissent
        # within the participating independent panel blocks acceptance.
        accepted = all(vote.accept for vote in votes)
        vote_digests = tuple(
            canonical_digest(
                {
                    "accept": vote.accept,
                    "authority_id": vote.authority_id,
                    "bundle_digest": vote.bundle_digest,
                    "evidence_digest": vote.evidence_digest,
                    "rationale_digest": vote.rationale_digest,
                }
            )
            for vote in votes
        )
        payload = {
            "accepted": accepted,
            "authority_ids": [vote.authority_id for vote in votes],
            "bundle_digest": bundle.digest,
            "vote_digests": list(vote_digests),
        }
        return GoldMasterVerdict(
            bundle_digest=bundle.digest,
            accepted=accepted,
            authority_ids=tuple(vote.authority_id for vote in votes),
            vote_digests=vote_digests,
            verdict_digest=canonical_digest(payload),
        )
