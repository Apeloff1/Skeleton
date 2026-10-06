"""Independent gold-master release arbitration for the AI game builder."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from .contracts import EffortMode, PromotionReceipt, canonical_digest


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
        if not isinstance(self.passed, bool):
            raise TypeError("family qualification passed state must be boolean")
        if not isinstance(self.evidence_digest, str) or len(self.evidence_digest) < 16:
            raise ValueError("family evidence digest must be stable")


@dataclass(frozen=True, slots=True)
class CriticalGateQualification:
    gate_id: str
    passed: bool
    evidence_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.gate_id, str) or not self.gate_id.strip():
            raise ValueError("critical gate id must be non-empty")
        if not isinstance(self.passed, bool):
            raise TypeError("critical gate passed state must be boolean")
        if not isinstance(self.evidence_digest, str) or len(self.evidence_digest) < 16:
            raise ValueError("critical gate evidence digest must be stable")


@dataclass(frozen=True, slots=True)
class ForgeReleaseBinding:
    """Content-addressed continuity proof from completed forge to release."""

    checkpoint_digest: str
    origin_champion_digest: str
    project_id: str
    run_id: str
    operation_id: str
    execution_id: str
    execution_identity_digest: str
    finalization_intent_digest: str
    model_identity_digest: str
    producer_behavior_digest: str
    source_revision: str
    champion_producer_provenance_digest: str
    champion_output_binding_digest: str
    champion_candidate_digest: str
    champion_artifact_digest: str
    champion_canon_digest: str
    champion_provenance_digest: str
    promotion_chain_digest: str
    effort_mode: EffortMode
    completed_rounds: int
    receipt_count: int

    def __post_init__(self) -> None:
        for name in (
            "checkpoint_digest",
            "origin_champion_digest",
            "execution_identity_digest",
            "finalization_intent_digest",
            "model_identity_digest",
            "producer_behavior_digest",
            "champion_producer_provenance_digest",
            "champion_output_binding_digest",
            "champion_candidate_digest",
            "promotion_chain_digest",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(ch not in "0123456789abcdef" for ch in value)
            ):
                raise ValueError(f"{name} must be lowercase sha256")
        for name in (
            "champion_artifact_digest",
            "champion_canon_digest",
            "champion_provenance_digest",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) < 16:
                raise ValueError(f"{name} must be a stable digest")
        for name in ("project_id", "run_id", "operation_id", "execution_id", "source_revision"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
        if len(self.source_revision) not in {40, 64} or any(
            ch not in "0123456789abcdef"
            for ch in self.source_revision
        ):
            raise ValueError("source_revision must be a lowercase git object id")
        if not isinstance(self.effort_mode, EffortMode):
            raise TypeError("forge release effort_mode must be EffortMode")
        if self.completed_rounds != self.effort_mode.rounds:
            raise ValueError("forge release binding requires exact completed effort budget")
        if self.receipt_count != self.completed_rounds:
            raise ValueError("forge release binding requires one receipt per completed round")

    @classmethod
    def from_checkpoint(
        cls,
        checkpoint: Mapping[str, object],
        *,
        expected_checkpoint_digest: str,
        receipts: Iterable[PromotionReceipt],
    ) -> "ForgeReleaseBinding":
        if not isinstance(checkpoint, Mapping):
            raise TypeError("forge checkpoint must be a mapping")
        if (
            not isinstance(expected_checkpoint_digest, str)
            or len(expected_checkpoint_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in expected_checkpoint_digest)
        ):
            raise ValueError("expected checkpoint digest must be lowercase sha256")
        supplied_digest = checkpoint.get("checkpoint_digest")
        if supplied_digest != expected_checkpoint_digest:
            raise ValueError(
                "forge release checkpoint does not match trusted external anchor"
            )
        core = {
            key: value
            for key, value in checkpoint.items()
            if key != "checkpoint_digest"
        }
        if not isinstance(supplied_digest, str) or supplied_digest != canonical_digest(core):
            raise ValueError("forge release checkpoint digest mismatch")
        if checkpoint.get("schema") != "skeleton.ai_game_builder.dual_rival_checkpoint.v1":
            raise ValueError("forge release checkpoint schema is unsupported")

        effort_mode = EffortMode.parse(checkpoint.get("effort_mode"))
        completed_rounds = checkpoint.get("completed_rounds")
        round_index = checkpoint.get("round_index")
        if isinstance(completed_rounds, bool) or not isinstance(completed_rounds, int):
            raise TypeError("forge release completed_rounds must be an integer")
        if isinstance(round_index, bool) or not isinstance(round_index, int):
            raise TypeError("forge release round_index must be an integer")
        if completed_rounds != effort_mode.rounds or round_index != effort_mode.rounds:
            raise ValueError("forge release checkpoint is not at exact terminal round")
        origin_champion_digest = checkpoint.get("origin_champion_digest")
        if (
            not isinstance(origin_champion_digest, str)
            or len(origin_champion_digest) != 64
            or any(ch not in "0123456789abcdef" for ch in origin_champion_digest)
        ):
            raise ValueError("forge release origin champion digest is invalid")
        if checkpoint.get("stage") != "construct":
            raise ValueError("forge release checkpoint must rest at construct boundary")
        if checkpoint.get("pending_construct") is not None or checkpoint.get("pending_challenge") is not None:
            raise ValueError("forge release checkpoint cannot contain pending round state")

        receipt_digests = checkpoint.get("receipt_digests")
        if not isinstance(receipt_digests, list):
            raise TypeError("forge release receipt digest chain must be a list")
        materialized_receipts = tuple(receipts)
        if any(not isinstance(item, PromotionReceipt) for item in materialized_receipts):
            raise TypeError("forge release receipts must contain PromotionReceipt values")
        actual_receipt_digests = [
            receipt.decision_digest
            for receipt in materialized_receipts
        ]
        if actual_receipt_digests != receipt_digests:
            raise ValueError("forge release receipts do not match checkpoint chain")
        if len(materialized_receipts) != completed_rounds:
            raise ValueError("forge release receipt chain must cover every completed round")
        if len(actual_receipt_digests) != len(set(actual_receipt_digests)):
            raise ValueError("forge release receipt digests must be unique")

        previous_promoted_digest: str | None = None
        for expected_round, receipt in enumerate(materialized_receipts, start=1):
            if receipt.round_index != expected_round:
                raise ValueError("forge release receipt rounds must form exact 1..N sequence")
            if receipt.effort_mode is not effort_mode:
                raise ValueError("forge release receipt effort mode mismatch")
            if expected_round == 1 and receipt.incumbent_digest != origin_champion_digest:
                raise ValueError(
                    "forge release first receipt does not match origin champion"
                )
            if (
                previous_promoted_digest is not None
                and receipt.incumbent_digest != previous_promoted_digest
            ):
                raise ValueError("forge release receipt winner chain is discontinuous")
            previous_promoted_digest = receipt.promoted_digest

        champion = checkpoint.get("champion")
        if not isinstance(champion, Mapping):
            raise ValueError("forge release checkpoint champion is missing")
        producer_provenance = champion.get("producer_provenance")
        if not isinstance(producer_provenance, Mapping):
            raise ValueError("forge release champion producer provenance is missing")
        project_id = producer_provenance.get("project_id")
        run_id = producer_provenance.get("run_id")
        if checkpoint.get("project_id") != project_id:
            raise ValueError("forge release project scope does not match champion provenance")
        if checkpoint.get("run_id") != run_id:
            raise ValueError("forge release run scope does not match champion provenance")
        artifact = champion.get("artifact")
        if not isinstance(artifact, Mapping):
            raise ValueError("forge release checkpoint champion artifact is missing")
        identities: dict[str, str] = {}
        for key in ("artifact_digest", "canon_digest", "provenance_digest"):
            value = artifact.get(key)
            if not isinstance(value, str) or len(value) < 16:
                raise ValueError(f"forge release champion {key} is invalid")
            identities[key] = value

        champion_candidate_digest = canonical_digest(champion)
        if previous_promoted_digest != champion_candidate_digest:
            raise ValueError("forge release terminal receipt does not match champion")
        required_provenance_text = {
            name: producer_provenance.get(name)
            for name in ("project_id", "run_id", "operation_id", "execution_id", "source_revision")
        }
        if any(
            not isinstance(value, str) or not value.strip()
            for value in required_provenance_text.values()
        ):
            raise ValueError("forge release champion producer text identity is incomplete")
        required_provenance_digests = {
            name: producer_provenance.get(name)
            for name in (
                "execution_identity_digest",
                "finalization_intent_digest",
                "model_identity_digest",
                "producer_behavior_digest",
                "output_binding_digest",
            )
        }
        if any(
            not isinstance(value, str)
            or len(value) != 64
            or any(ch not in "0123456789abcdef" for ch in value)
            for value in required_provenance_digests.values()
        ):
            raise ValueError("forge release champion producer digest identity is incomplete")

        return cls(
            checkpoint_digest=supplied_digest,
            origin_champion_digest=origin_champion_digest,
            project_id=required_provenance_text["project_id"],
            run_id=required_provenance_text["run_id"],
            operation_id=required_provenance_text["operation_id"],
            execution_id=required_provenance_text["execution_id"],
            execution_identity_digest=required_provenance_digests["execution_identity_digest"],
            finalization_intent_digest=required_provenance_digests["finalization_intent_digest"],
            model_identity_digest=required_provenance_digests["model_identity_digest"],
            producer_behavior_digest=required_provenance_digests["producer_behavior_digest"],
            source_revision=required_provenance_text["source_revision"],
            champion_producer_provenance_digest=canonical_digest(producer_provenance),
            champion_output_binding_digest=required_provenance_digests["output_binding_digest"],
            champion_candidate_digest=champion_candidate_digest,
            champion_artifact_digest=identities["artifact_digest"],
            champion_canon_digest=identities["canon_digest"],
            champion_provenance_digest=identities["provenance_digest"],
            promotion_chain_digest=canonical_digest(actual_receipt_digests),
            effort_mode=effort_mode,
            completed_rounds=completed_rounds,
            receipt_count=len(materialized_receipts),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "checkpoint_digest": self.checkpoint_digest,
            "origin_champion_digest": self.origin_champion_digest,
            "project_id": self.project_id,
            "run_id": self.run_id,
            "operation_id": self.operation_id,
            "execution_id": self.execution_id,
            "execution_identity_digest": self.execution_identity_digest,
            "finalization_intent_digest": self.finalization_intent_digest,
            "model_identity_digest": self.model_identity_digest,
            "producer_behavior_digest": self.producer_behavior_digest,
            "source_revision": self.source_revision,
            "champion_producer_provenance_digest": self.champion_producer_provenance_digest,
            "champion_output_binding_digest": self.champion_output_binding_digest,
            "champion_artifact_digest": self.champion_artifact_digest,
            "champion_candidate_digest": self.champion_candidate_digest,
            "champion_canon_digest": self.champion_canon_digest,
            "champion_provenance_digest": self.champion_provenance_digest,
            "completed_rounds": self.completed_rounds,
            "effort_mode": int(self.effort_mode),
            "promotion_chain_digest": self.promotion_chain_digest,
            "receipt_count": self.receipt_count,
        }

    @property
    def digest(self) -> str:
        return canonical_digest(self.to_payload())


@dataclass(frozen=True, slots=True)
class GoldMasterBundle:
    artifact_digest: str
    build_digest: str
    canon_digest: str
    provenance_digest: str
    replay_digest: str
    rollback_target_digest: str
    red_team_digest: str
    forge_binding: ForgeReleaseBinding
    family_qualifications: tuple[FamilyQualification, ...]
    critical_gate_qualifications: tuple[CriticalGateQualification, ...]

    def __post_init__(self) -> None:
        for value in (
            self.artifact_digest,
            self.build_digest,
            self.canon_digest,
            self.provenance_digest,
            self.replay_digest,
            self.rollback_target_digest,
            self.red_team_digest,
        ):
            if not isinstance(value, str) or len(value) < 16:
                raise ValueError("gold-master identities must be stable digests")
        if not isinstance(self.forge_binding, ForgeReleaseBinding):
            raise TypeError("gold-master bundle requires ForgeReleaseBinding")
        if self.artifact_digest != self.forge_binding.champion_artifact_digest:
            raise ValueError("gold-master artifact must match forge champion artifact")
        if self.canon_digest != self.forge_binding.champion_canon_digest:
            raise ValueError("gold-master canon must match forge champion canon")
        if self.provenance_digest != self.forge_binding.champion_provenance_digest:
            raise ValueError("gold-master provenance must match forge champion provenance")
        if any(
            not isinstance(row, FamilyQualification)
            for row in self.family_qualifications
        ):
            raise TypeError(
                "gold-master family qualifications must contain FamilyQualification values"
            )
        expected_families = [f"GB{i:02d}" for i in range(1, 51)]
        if [row.family_id for row in self.family_qualifications] != expected_families:
            raise ValueError("gold-master bundle requires exactly GB01..GB50")
        if any(
            not isinstance(row, CriticalGateQualification)
            for row in self.critical_gate_qualifications
        ):
            raise TypeError(
                "gold-master critical gates must contain CriticalGateQualification values"
            )
        if not self.critical_gate_qualifications:
            raise ValueError("gold-master bundle requires critical gates")
        gate_ids = [row.gate_id for row in self.critical_gate_qualifications]
        if gate_ids != sorted(gate_ids):
            raise ValueError("gold-master critical gates must use canonical order")
        if len(gate_ids) != len(set(gate_ids)):
            raise ValueError("gold-master critical gate ids must be unique")

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
        forge_binding: ForgeReleaseBinding,
        family_qualifications: Iterable[FamilyQualification],
        critical_gate_results: Mapping[str, tuple[bool, str]],
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

        gates: list[CriticalGateQualification] = []
        for gate_id in sorted(critical_gate_results):
            raw = critical_gate_results[gate_id]
            if (
                not isinstance(raw, tuple)
                or len(raw) != 2
                or not isinstance(raw[0], bool)
                or not isinstance(raw[1], str)
            ):
                raise ValueError(
                    "critical gate result must be a (passed, evidence_digest) tuple"
                )
            gates.append(
                CriticalGateQualification(
                    gate_id=str(gate_id),
                    passed=raw[0],
                    evidence_digest=raw[1],
                )
            )
        if not gates:
            raise ValueError("gold-master bundle requires critical gates")

        return cls(
            artifact_digest=artifact_digest,
            build_digest=build_digest,
            canon_digest=canon_digest,
            provenance_digest=provenance_digest,
            replay_digest=replay_digest,
            rollback_target_digest=rollback_target_digest,
            red_team_digest=red_team_digest,
            forge_binding=forge_binding,
            family_qualifications=families,
            critical_gate_qualifications=tuple(gates),
        )

    @property
    def eligible(self) -> bool:
        return all(row.passed for row in self.family_qualifications) and all(
            row.passed for row in self.critical_gate_qualifications
        )

    @property
    def digest(self) -> str:
        return canonical_digest(
            {
                "artifact_digest": self.artifact_digest,
                "build_digest": self.build_digest,
                "canon_digest": self.canon_digest,
                "critical_gate_qualifications": [
                    {
                        "evidence_digest": row.evidence_digest,
                        "gate_id": row.gate_id,
                        "passed": row.passed,
                    }
                    for row in self.critical_gate_qualifications
                ],
                "forge_binding": self.forge_binding.to_payload(),
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
        if not isinstance(self.authority_id, str) or not self.authority_id.strip():
            raise ValueError("authority_id must be non-empty")
        if not isinstance(self.accept, bool):
            raise TypeError("tribunal vote accept state must be boolean")
        for value in (self.bundle_digest, self.evidence_digest, self.rationale_digest):
            if not isinstance(value, str) or len(value) < 16:
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
        routine_evaluator_ids: Iterable[str] = (),
        forbidden_ids: Iterable[str] = ("rival_a", "rival_b"),
    ) -> None:
        ids = tuple(str(x).strip() for x in authority_ids)
        forbidden = {
            *(str(x).strip() for x in forbidden_ids),
            *(str(x).strip() for x in routine_evaluator_ids),
        }
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
            raise ReleaseArbitrationError(
                "gold-master bundle has failed family or critical-gate qualification"
            )
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
