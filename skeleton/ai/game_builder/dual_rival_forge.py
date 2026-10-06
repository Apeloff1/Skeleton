"""Deterministic state machine for the two-rival game-builder forge.

This module does not call models. It governs the control plane around model
candidates so model/provider adapters cannot bypass stage order, role rotation,
hard-gate promotion, checkpointing, or effort-mode limits.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from .contracts import (
    ArtifactIdentity,
    Candidate,
    Challenge,
    EffortMode,
    GateResult,
    PromotionReceipt,
    Rival,
    Stage,
    canonical_digest,
    promotion_receipt,
)


class ForgeStateError(RuntimeError):
    pass


def _candidate_from_payload(payload: Mapping[str, object]) -> Candidate:
    artifact_payload = payload.get("artifact")
    quality = payload.get("quality")
    if not isinstance(artifact_payload, Mapping):
        raise ForgeStateError("candidate artifact payload missing")
    if not isinstance(quality, Mapping):
        raise ForgeStateError("candidate quality payload missing")
    artifact = ArtifactIdentity(
        artifact_digest=str(artifact_payload["artifact_digest"]),
        canon_digest=str(artifact_payload["canon_digest"]),
        provenance_digest=str(artifact_payload["provenance_digest"]),
        family_id=str(artifact_payload["family_id"]),
        level_id=str(artifact_payload["level_id"]),
    )
    evidence = payload.get("evidence_digests", ())
    parents = payload.get("parent_candidate_digests", ())
    if not isinstance(evidence, list) or not isinstance(parents, list):
        raise ForgeStateError("candidate lineage/evidence payload malformed")
    return Candidate.create(
        producer_id=str(payload["producer_id"]),
        artifact=artifact,
        quality={str(k): float(v) for k, v in quality.items()},
        evidence_digests=[str(x) for x in evidence],
        assumption_digest=str(payload["assumption_digest"]),
        parent_candidate_digests=[str(x) for x in parents],
    )


def _challenge_from_payload(payload: Mapping[str, object]) -> Challenge:
    improved = payload.get("improved_candidate")
    counters = payload.get("counterexample_digests")
    if not isinstance(improved, Mapping) or not isinstance(counters, list):
        raise ForgeStateError("challenge payload malformed")
    return Challenge(
        challenger_id=str(payload["challenger_id"]),
        target_candidate_digest=str(payload["target_candidate_digest"]),
        attack_digest=str(payload["attack_digest"]),
        improved_candidate=_candidate_from_payload(improved),
        counterexample_digests=tuple(str(x) for x in counters),
    )


@dataclass(frozen=True, slots=True)
class ForgeStatus:
    effort_mode: EffortMode
    round_index: int
    completed_rounds: int
    remaining_rounds: int
    builder: Rival
    challenger: Rival
    stage: Stage
    champion_digest: str
    completed: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "builder": self.builder.value,
            "challenger": self.challenger.value,
            "champion_digest": self.champion_digest,
            "completed": self.completed,
            "completed_rounds": self.completed_rounds,
            "effort_mode": int(self.effort_mode),
            "remaining_rounds": self.remaining_rounds,
            "round_index": self.round_index,
            "stage": self.stage.value,
        }


class DualRivalForge:
    """Pure deterministic control-plane state machine.

    One round is always:
      construct -> attack_and_improve -> reconcile_and_promote

    Role rotation occurs only after a fully reconciled round. There is no
    wall-clock deadline anywhere in this state machine.
    """

    SCHEMA = "skeleton.ai_game_builder.dual_rival_checkpoint.v1"

    def __init__(
        self,
        *,
        effort_mode: EffortMode | int | str,
        champion: Candidate,
        builder: Rival = Rival.A,
        round_index: int = 1,
        completed_rounds: int = 0,
        stage: Stage = Stage.CONSTRUCT,
        pending_construct: Candidate | None = None,
        pending_challenge: Challenge | None = None,
        receipts: Sequence[PromotionReceipt] = (),
    ) -> None:
        self.effort_mode = EffortMode.parse(effort_mode)
        self.champion = champion
        self.builder = builder
        self.challenger = builder.other
        self.round_index = round_index
        self.completed_rounds = completed_rounds
        self.stage = stage
        self.pending_construct = pending_construct
        self.pending_challenge = pending_challenge
        self.receipts = list(receipts)
        self._validate_state()

    @property
    def completed(self) -> bool:
        return self.completed_rounds >= self.effort_mode.rounds

    @property
    def status(self) -> ForgeStatus:
        return ForgeStatus(
            effort_mode=self.effort_mode,
            round_index=self.round_index,
            completed_rounds=self.completed_rounds,
            remaining_rounds=max(0, self.effort_mode.rounds - self.completed_rounds),
            builder=self.builder,
            challenger=self.challenger,
            stage=self.stage,
            champion_digest=self.champion.digest,
            completed=self.completed,
        )

    def _validate_state(self) -> None:
        if len(self.receipts) != self.completed_rounds:
            raise ForgeStateError(
                "completed_rounds must equal promotion receipt count"
            )
        previous_promoted_digest: str | None = None
        for expected_round, receipt in enumerate(self.receipts, start=1):
            if not isinstance(receipt, PromotionReceipt):
                raise ForgeStateError(
                    "promotion history must contain PromotionReceipt values"
                )
            if receipt.round_index != expected_round:
                raise ForgeStateError(
                    "promotion receipt rounds must form exact 1..N sequence"
                )
            if receipt.effort_mode is not self.effort_mode:
                raise ForgeStateError(
                    "promotion receipt effort mode must match forge effort mode"
                )
            if (
                previous_promoted_digest is not None
                and receipt.incumbent_digest != previous_promoted_digest
            ):
                raise ForgeStateError(
                    "promotion receipt chain incumbent does not match prior winner"
                )
            previous_promoted_digest = receipt.promoted_digest
        if (
            previous_promoted_digest is not None
            and self.champion.digest != previous_promoted_digest
        ):
            raise ForgeStateError(
                "forge champion must match terminal promotion receipt"
            )
        if self.round_index < 1:
            raise ForgeStateError("round_index must be positive")
        if not 0 <= self.completed_rounds <= self.effort_mode.rounds:
            raise ForgeStateError("completed_rounds outside effort-mode bounds")
        if self.completed:
            if self.completed_rounds != self.effort_mode.rounds:
                raise ForgeStateError("completed state must equal exact round budget")
            if self.stage is not Stage.CONSTRUCT:
                raise ForgeStateError("completed forge must rest at construct boundary")
            if self.pending_construct is not None or self.pending_challenge is not None:
                raise ForgeStateError("completed forge cannot retain pending round state")
            return
        if self.round_index != self.completed_rounds + 1:
            raise ForgeStateError("round_index must equal completed_rounds + 1")
        if self.stage is Stage.CONSTRUCT:
            if self.pending_construct is not None or self.pending_challenge is not None:
                raise ForgeStateError("construct stage cannot have pending state")
        elif self.stage is Stage.ATTACK_AND_IMPROVE:
            if self.pending_construct is None or self.pending_challenge is not None:
                raise ForgeStateError("attack stage requires exactly one constructed candidate")
        elif self.stage is Stage.RECONCILE_AND_PROMOTE:
            if self.pending_construct is None or self.pending_challenge is None:
                raise ForgeStateError("reconcile stage requires candidate and challenge")

    def submit_construct(self, candidate: Candidate) -> ForgeStatus:
        if self.completed:
            raise ForgeStateError("effort-mode round budget is complete")
        if self.stage is not Stage.CONSTRUCT:
            raise ForgeStateError("construct submission is out of stage order")
        if candidate.producer_id != self.builder.value:
            raise ForgeStateError("construct candidate must come from current builder")
        self.pending_construct = candidate
        self.stage = Stage.ATTACK_AND_IMPROVE
        return self.status

    def submit_attack(self, challenge: Challenge) -> ForgeStatus:
        if self.completed:
            raise ForgeStateError("effort-mode round budget is complete")
        if self.stage is not Stage.ATTACK_AND_IMPROVE or self.pending_construct is None:
            raise ForgeStateError("attack submission is out of stage order")
        if challenge.challenger_id != self.challenger.value:
            raise ForgeStateError("challenge must come from current challenger")
        if challenge.target_candidate_digest != self.pending_construct.digest:
            raise ForgeStateError("challenge target does not match constructed candidate")
        if challenge.improved_candidate.producer_id != self.challenger.value:
            raise ForgeStateError("improved candidate must be authored by challenger")
        self.pending_challenge = challenge
        self.stage = Stage.RECONCILE_AND_PROMOTE
        return self.status

    def _eligible_reconcile_candidate(self, candidate: Candidate | None) -> None:
        if candidate is None:
            return
        assert self.pending_construct is not None
        assert self.pending_challenge is not None
        direct = {
            self.pending_construct.digest,
            self.pending_challenge.improved_candidate.digest,
        }
        if candidate.digest in direct:
            return
        parents = set(candidate.parent_candidate_digests)
        if not direct.issubset(parents):
            raise ForgeStateError(
                "synthesis candidate must name both constructed and challenged parents"
            )
        if candidate.producer_id in {self.builder.value, self.challenger.value}:
            raise ForgeStateError(
                "synthesis must use an explicit synthesis producer identity"
            )

    def reconcile(
        self,
        *,
        submitted: Candidate | None,
        evaluator_id: str,
        gate_results: Sequence[GateResult],
        protected_axes: Iterable[str] | None = None,
        evaluated_quality: Mapping[str, float] | None = None,
    ) -> PromotionReceipt:
        if self.completed:
            raise ForgeStateError("effort-mode round budget is complete")
        if (
            self.stage is not Stage.RECONCILE_AND_PROMOTE
            or self.pending_construct is None
            or self.pending_challenge is None
        ):
            raise ForgeStateError("reconcile submission is out of stage order")
        self._eligible_reconcile_candidate(submitted)
        kwargs = {}
        if protected_axes is not None:
            kwargs["protected_axes"] = protected_axes
        receipt = promotion_receipt(
            round_index=self.round_index,
            effort_mode=self.effort_mode,
            incumbent=self.champion,
            submitted=submitted,
            evaluator_id=evaluator_id,
            gate_results=gate_results,
            submitted_quality_override=evaluated_quality,
            **kwargs,
        )
        if receipt.decision == "promote":
            if submitted is None:
                raise ForgeStateError("promotion receipt cannot promote null candidate")
            self.champion = submitted
        self.receipts.append(receipt)
        self._close_round()
        return receipt

    def _close_round(self) -> None:
        self.completed_rounds += 1
        self.pending_construct = None
        self.pending_challenge = None
        self.stage = Stage.CONSTRUCT
        self.builder = self.builder.other
        self.challenger = self.builder.other
        if self.completed_rounds < self.effort_mode.rounds:
            self.round_index = self.completed_rounds + 1
        else:
            # Keep a deterministic terminal index equal to the completed budget.
            self.round_index = self.effort_mode.rounds
        self._validate_state()

    def release_binding(self):
        """Build the terminal forge-to-release continuity proof."""

        if not self.completed:
            raise ForgeStateError("forge release binding requires completed effort budget")
        from .release import ForgeReleaseBinding

        return ForgeReleaseBinding.from_checkpoint(
            self.checkpoint(),
            receipts=self.receipts,
        )

    def checkpoint(self) -> dict[str, object]:
        pending_challenge: dict[str, object] | None = None
        if self.pending_challenge is not None:
            pending_challenge = {
                "attack_digest": self.pending_challenge.attack_digest,
                "challenger_id": self.pending_challenge.challenger_id,
                "counterexample_digests": list(
                    self.pending_challenge.counterexample_digests
                ),
                "improved_candidate": self.pending_challenge.improved_candidate.to_payload(),
                "target_candidate_digest": self.pending_challenge.target_candidate_digest,
            }
        core: dict[str, object] = {
            "builder": self.builder.value,
            "champion": self.champion.to_payload(),
            "completed_rounds": self.completed_rounds,
            "effort_mode": int(self.effort_mode),
            "pending_challenge": pending_challenge,
            "pending_construct": (
                self.pending_construct.to_payload()
                if self.pending_construct is not None
                else None
            ),
            "receipt_digests": [receipt.decision_digest for receipt in self.receipts],
            "round_index": self.round_index,
            "schema": self.SCHEMA,
            "stage": self.stage.value,
        }
        return {**core, "checkpoint_digest": canonical_digest(core)}

    @classmethod
    def restore(
        cls,
        checkpoint: Mapping[str, object],
        *,
        receipts: Sequence[PromotionReceipt] = (),
    ) -> "DualRivalForge":
        supplied_digest = checkpoint.get("checkpoint_digest")
        core = {key: value for key, value in checkpoint.items() if key != "checkpoint_digest"}
        if supplied_digest != canonical_digest(core):
            raise ForgeStateError("checkpoint digest mismatch")
        if checkpoint.get("schema") != cls.SCHEMA:
            raise ForgeStateError("unsupported checkpoint schema")

        champion_payload = checkpoint.get("champion")
        if not isinstance(champion_payload, Mapping):
            raise ForgeStateError("checkpoint champion is missing")
        pending_construct_payload = checkpoint.get("pending_construct")
        pending_challenge_payload = checkpoint.get("pending_challenge")
        pending_construct = (
            _candidate_from_payload(pending_construct_payload)
            if isinstance(pending_construct_payload, Mapping)
            else None
        )
        pending_challenge = (
            _challenge_from_payload(pending_challenge_payload)
            if isinstance(pending_challenge_payload, Mapping)
            else None
        )
        expected_receipt_digests = checkpoint.get("receipt_digests")
        if not isinstance(expected_receipt_digests, list):
            raise ForgeStateError("checkpoint receipt digest list is malformed")
        actual_receipt_digests = [receipt.decision_digest for receipt in receipts]
        if actual_receipt_digests != [str(x) for x in expected_receipt_digests]:
            raise ForgeStateError("promotion receipt chain does not match checkpoint")

        return cls(
            effort_mode=EffortMode.parse(checkpoint["effort_mode"]),
            champion=_candidate_from_payload(champion_payload),
            builder=Rival(str(checkpoint["builder"])),
            round_index=int(checkpoint["round_index"]),
            completed_rounds=int(checkpoint["completed_rounds"]),
            stage=Stage(str(checkpoint["stage"])),
            pending_construct=pending_construct,
            pending_challenge=pending_challenge,
            receipts=receipts,
        )
