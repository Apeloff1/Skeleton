"""Adversarial verifier-of-verifiers for Jeeves' pre-delivery release gate.

This is deterministic mutation testing of independent host verifiers, not an
LLM claiming independent assurance. Attacks do not touch live run state.
Every required corruption must be rejected by its designated verifier.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Sequence

from .types import Goal, ToolObservation, stable_fingerprint
from .working_context_cycle import (
    IntegrityVerifier,
    NoFoundNote,
    PreparedDelivery,
    ScopeVerifier,
)


class VerifierAdversarialFailure(RuntimeError):
    """At least one mandatory adversarial challenge escaped detection."""


@dataclass(frozen=True, slots=True)
class VerifierAttack:
    target: str
    name: str
    rejected: bool
    mutation_digest: str
    rejection_reason: str

    @property
    def fingerprint(self) -> str:
        return stable_fingerprint({
            "target": self.target,
            "name": self.name,
            "rejected": self.rejected,
            "mutation": self.mutation_digest,
            "reason": self.rejection_reason,
        })


@dataclass(frozen=True, slots=True)
class AdversarialReviewReceipt:
    subject: str
    integrity_attacks: int
    scope_attacks: int
    attacks: tuple[VerifierAttack, ...]
    passed: bool

    @property
    def digest(self) -> str:
        return stable_fingerprint({
            "subject": self.subject,
            "integrity": self.integrity_attacks,
            "scope": self.scope_attacks,
            "attacks": [item.fingerprint for item in self.attacks],
            "passed": self.passed,
        })


IntegrityCallback = Callable[[PreparedDelivery, Goal, Sequence[ToolObservation]], None]
ScopeCallback = Callable[..., None]


class AdversarialVerifierReviewer:
    """Run a fixed, replayable attack suite against both actual release verifiers."""

    def __init__(
        self,
        *,
        integrity: IntegrityCallback | None = None,
        scope: ScopeCallback | None = None,
    ) -> None:
        # Custom callbacks are for deterministic adversarial regression; runtime
        # uses actual host verifiers, not model-supplied callbacks.
        self.integrity = integrity or IntegrityVerifier.verify
        self.scope = scope or ScopeVerifier.verify

    def review(
        self,
        prepared: PreparedDelivery,
        goal: Goal,
        observations: Sequence[ToolObservation],
        *,
        answer: str | None = None,
    ) -> AdversarialReviewReceipt:
        originals = tuple(observations)
        # Genuine unmodified subject must be accepted first.
        self.integrity(prepared, goal, originals)
        self.scope(prepared, goal, originals, answer=answer)
        attacks: list[VerifierAttack] = []

        def attack_integrity(
            name: str, mutated: PreparedDelivery,
            *, changed_goal: Goal | None = None,
        ) -> None:
            caught = False
            reason = "verifier incorrectly accepted mutation"
            try:
                self.integrity(mutated, changed_goal or goal, originals)
            except (ValueError, TypeError, AssertionError) as exc:
                caught = True
                reason = type(exc).__name__ + ": " + str(exc)[:180]
            attacks.append(VerifierAttack(
                "integrity", name, caught, mutated.fingerprint, reason,
            ))

        def attack_scope(
            name: str, mutated: PreparedDelivery, *, changed_answer: str | None = None
        ) -> None:
            caught = False
            reason = "verifier incorrectly accepted mutation"
            try:
                self.scope(
                    mutated, goal, originals,
                    answer=answer if changed_answer is None else changed_answer,
                )
            except (ValueError, TypeError, AssertionError) as exc:
                caught = True
                reason = type(exc).__name__ + ": " + str(exc)[:180]
            attacks.append(VerifierAttack(
                "scope", name, caught, mutated.fingerprint, reason,
            ))

        # Integrity: preserve pinned user goal, all original observations,
        # active evidence, page counter and semantically bound chain.
        corrupted_digests = (("mutated-call", "0" * 64),)
        attack_integrity("source_fingerprint_forgery",
                         replace(prepared, original_digests=corrupted_digests))
        attack_integrity("goal_replacement", prepared, changed_goal=replace(
            goal, objective=goal.objective + " [adversarial drift]"
        ))
        attack_integrity("page_counter_forgery", replace(
            prepared, page_count=prepared.page_count + 1
        ))
        attack_integrity("goal_policy_downgrade", prepared, changed_goal=replace(
            goal, metadata={**goal.metadata, "delivery_kind": "non_code"}
        ))
        attack_integrity("fabricated_compaction_savings", replace(
            prepared, freed_chars=prepared.freed_chars + 1
        ))
        if prepared.active_observations:
            active = prepared.active_observations[0]
            corrupted_active = replace(prepared, active_observations=(
                replace(active, payload={"forged": True}),
                *prepared.active_observations[1:],
            ))
            attack_integrity("reused_id_modified_result", corrupted_active)
            attack_scope("reused_id_modified_result", corrupted_active)
        if originals:
            attack_integrity("lost_live_observation", replace(
                prepared, active_observations=()
                if prepared.active_observations else (originals[0],)
            ))
        if prepared.notes:
            attack_integrity("deleted_no_found_note", replace(
                prepared, notes=prepared.notes[1:]
            ))
            attack_integrity("forged_note_source", replace(
                prepared, notes=(replace(prepared.notes[0], source_digest="0" * 64),)
                + prepared.notes[1:]
            ))
            first = prepared.receipts[0]
            attack_integrity("receipt_action_tamper", replace(
                prepared, receipts=(replace(first, action="exonerated"),)
                + prepared.receipts[1:]
            ))

        # Independent scope checks: fake search authority, source scope drift,
        # capacity limits, unsupported nonexistence claims.
        fake_note = NoFoundNote("unobserved-call", "lookup",
                                "all repositories", "0" * 64,
                                "JVS-000001-P000001")
        attack_scope("fabricated_no_found_observation", replace(
            prepared, notes=prepared.notes + (fake_note,)
        ))
        if prepared.notes:
            attack_scope("enlarged_negative_scope", replace(
                prepared, notes=(replace(prepared.notes[0], scope="all systems"),)
                + prepared.notes[1:]
            ))
            attack_scope("unqualified_global_absence", prepared,
                         changed_answer="This system never existed.")
            attack_scope("lost_scope_warning", replace(
                prepared, notes=(replace(prepared.notes[0], tool_name="fabricated"),)
                + prepared.notes[1:]
            ))
        else:
            attack_scope("unauthorized_refill", replace(
                prepared, refill="unverified and invented context"
            ))

        integrity_count = sum(x.target == "integrity" for x in attacks)
        scope_count = sum(x.target == "scope" for x in attacks)
        receipt = AdversarialReviewReceipt(
            subject=stable_fingerprint({
                "prepared": prepared.fingerprint, "goal": goal.goal_id,
                "source": prepared.original_digests,
                "answer": answer,
            }),
            integrity_attacks=integrity_count,
            scope_attacks=scope_count,
            attacks=tuple(attacks),
            passed=all(item.rejected for item in attacks),
        )
        if integrity_count < 3 or scope_count < 2 or not receipt.passed:
            names = [f"{x.target}:{x.name}" for x in attacks if not x.rejected]
            raise VerifierAdversarialFailure(
                "verifier-of-verifiers caught unsafe acceptance: "
                + ", ".join(names or ("attack coverage insufficient",))
            )
        return receipt
