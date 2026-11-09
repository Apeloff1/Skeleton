"""P0 formal targets for VOL-081.

These finite models are deliberately small enough for exhaustive exploration
and high-consequence enough to justify formal treatment:

* canonical operation lifecycle authority/order;
* canonical protocol replay/idempotency behavior.

The model definitions are independent of implementation control flow. Separate
conformance functions compare the model transition relation with the named
production contracts bound into each specification.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from .formal_methods import (
    BoundedModelChecker,
    FormalAssumption,
    FormalMethodError,
    FormalRunReport,
    FormalSpecification,
    FormalState,
    ImplementationBinding,
    ModelSemantics,
    ObligationKind,
    ProofObligation,
    StateVariable,
    TransitionCandidate,
)
from .operation import (
    OperationEnvelope,
    OperationState,
    OperationTransitionError,
    TERMINAL_OPERATION_STATES,
)
from .protocol import (
    ProtocolContractError,
    ProtocolEnvelope,
    ProtocolReplayGuard,
    RetryClass,
    UnknownOutcomePolicy,
)

_OPERATION_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "created": ("validated", "failed", "cancelled"),
    "validated": ("authorized", "failed", "cancelled"),
    "authorized": ("admitted", "failed", "cancelled"),
    "admitted": ("queued", "running", "failed", "cancelled"),
    "queued": ("running", "failed", "cancelled"),
    "running": (
        "waiting_for_tool",
        "waiting_for_user",
        "retrying",
        "degraded",
        "completed",
        "failed",
        "cancelled",
    ),
    "waiting_for_tool": (
        "running",
        "retrying",
        "failed",
        "cancelled",
    ),
    "waiting_for_user": ("running", "failed", "cancelled"),
    "retrying": (
        "running",
        "degraded",
        "failed",
        "cancelled",
    ),
    "degraded": (
        "running",
        "retrying",
        "completed",
        "failed",
        "cancelled",
    ),
    "completed": (),
    "failed": (),
    "cancelled": (),
}

_TERMINAL_NAMES = frozenset(item.value for item in TERMINAL_OPERATION_STATES)
_POST_AUTHORIZATION = frozenset(
    {
        "admitted",
        "queued",
        "running",
        "waiting_for_tool",
        "waiting_for_user",
        "retrying",
        "degraded",
        "completed",
    }
)
_POST_ADMISSION = frozenset(
    {
        "queued",
        "running",
        "waiting_for_tool",
        "waiting_for_user",
        "retrying",
        "degraded",
        "completed",
    }
)


def _state(**values: object) -> FormalState:
    return FormalState.from_mapping(values)


def _operation_initial(state: FormalState) -> bool:
    values = state.to_mapping()
    return (
        values["lifecycle"] == "created"
        and values["authorized_seen"] is False
        and values["admitted_seen"] is False
    )


def _operation_terminal(state: FormalState) -> bool:
    return state.get("lifecycle") in _TERMINAL_NAMES


def _operation_transitions(state: FormalState) -> tuple[TransitionCandidate, ...]:
    values = state.to_mapping()
    lifecycle = str(values["lifecycle"])
    authorized_seen = bool(values["authorized_seen"])
    admitted_seen = bool(values["admitted_seen"])
    candidates: list[TransitionCandidate] = []
    for target in _OPERATION_TRANSITIONS[lifecycle]:
        next_authorized = authorized_seen or target == "authorized"
        next_admitted = admitted_seen or target == "admitted"
        candidates.append(
            TransitionCandidate(
                action=f"transition:{target}",
                next_state=_state(
                    lifecycle=target,
                    authorized_seen=next_authorized,
                    admitted_seen=next_admitted,
                ),
            )
        )
    return tuple(candidates)


def _operation_authority_invariant(state: FormalState) -> bool:
    lifecycle = str(state.get("lifecycle"))
    authorized_seen = bool(state.get("authorized_seen"))
    admitted_seen = bool(state.get("admitted_seen"))
    if lifecycle in _POST_AUTHORIZATION and not authorized_seen:
        return False
    if lifecycle in _POST_ADMISSION and not admitted_seen:
        return False
    if admitted_seen and not authorized_seen:
        return False
    return True


def _operation_transition_history(
    before: FormalState,
    after: FormalState,
    action: str,
) -> bool:
    target = action.removeprefix("transition:")
    if target != after.get("lifecycle"):
        return False
    if bool(before.get("authorized_seen")) and not bool(
        after.get("authorized_seen")
    ):
        return False
    if bool(before.get("admitted_seen")) and not bool(
        after.get("admitted_seen")
    ):
        return False
    return True


def _operation_completed(state: FormalState) -> bool:
    return state.get("lifecycle") == "completed"


def operation_lifecycle_specification() -> FormalSpecification:
    return FormalSpecification(
        spec_id="P0.OPERATION.LIFECYCLE",
        title="Canonical operation lifecycle authority and terminal safety",
        consequence_rank=5,
        ambiguity_rank=4,
        variables=(
            StateVariable(
                "lifecycle",
                tuple(item.value for item in OperationState),
            ),
            StateVariable("authorized_seen", (False, True)),
            StateVariable("admitted_seen", (False, True)),
        ),
        assumptions=(
            FormalAssumption(
                assumption_id="operation.single_transition",
                statement=(
                    "Each modeled step corresponds to one call to the "
                    "canonical OperationEnvelope.transition contract."
                ),
                falsification_condition=(
                    "A production path mutates operation lifecycle without "
                    "using equivalent canonical transition semantics."
                ),
            ),
            FormalAssumption(
                assumption_id="operation.identity_stable",
                statement=(
                    "Operation identity fields do not change during lifecycle "
                    "transition checking."
                ),
                falsification_condition=(
                    "A lifecycle transition also rewrites operation identity."
                ),
            ),
        ),
        implementation_bindings=(
            ImplementationBinding.from_object(
                contract_id="OperationEnvelope.transition",
                obj=OperationEnvelope.transition,
                canonical_module_path="skeleton.contracts.operation",
                canonical_symbol="OperationEnvelope.transition",
            ),
        ),
        obligations=(
            ProofObligation(
                obligation_id="operation.authority_order",
                kind=ObligationKind.INVARIANT,
                statement=(
                    "Execution/admission/completion states cannot be reached "
                    "without prior authorization and admission history."
                ),
                predicate_name="operation_authority_invariant",
            ),
            ProofObligation(
                obligation_id="operation.history_monotonic",
                kind=ObligationKind.TRANSITION,
                statement=(
                    "Authorization/admission history is monotonic across "
                    "every lifecycle transition."
                ),
                predicate_name="operation_transition_history",
            ),
            ProofObligation(
                obligation_id="operation.no_nonterminal_deadlock",
                kind=ObligationKind.DEADLOCK_FREE,
                statement=(
                    "Every non-terminal operation lifecycle state has at "
                    "least one declared transition."
                ),
            ),
            ProofObligation(
                obligation_id="operation.completion_reachable",
                kind=ObligationKind.REACHABILITY,
                statement=(
                    "A completed operation is reachable from the canonical "
                    "created state under the declared lifecycle."
                ),
                predicate_name="operation_completed",
            ),
        ),
        initial_predicate_name="operation_initial",
        transition_relation_name="operation_transition_relation",
        terminal_predicate_name="operation_terminal",
        max_states=128,
        max_transitions=512,
        max_depth=16,
    )


def operation_lifecycle_semantics() -> ModelSemantics:
    return ModelSemantics(
        model_id="P0.OPERATION.LIFECYCLE.MODEL",
        initial_predicate_name="operation_initial",
        initial_predicate=_operation_initial,
        transition_relation_name="operation_transition_relation",
        transitions=_operation_transitions,
        predicates={
            "operation_authority_invariant": _operation_authority_invariant,
            "operation_transition_history": _operation_transition_history,
            "operation_completed": _operation_completed,
        },
        terminal_predicate_name="operation_terminal",
        terminal_predicate=_operation_terminal,
    )


def _sample_operation(state: str) -> OperationEnvelope:
    created = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return OperationEnvelope(
        operation_id=str(UUID(int=1)),
        tenant_id="formal-tenant",
        actor_id="formal-actor",
        capability="formal-check",
        created_at=created,
        deadline=created + timedelta(hours=1),
        idempotency_key="formal-idempotency",
        trace_id="formal-trace",
        state=OperationState(state),
    )


def verify_operation_transition_conformance() -> None:
    """Compare every formal lifecycle edge/non-edge to production behavior."""

    states = tuple(item.value for item in OperationState)
    for source in states:
        expected = set(_OPERATION_TRANSITIONS[source])
        envelope = _sample_operation(source)
        for target in states:
            accepted = True
            try:
                transitioned = envelope.transition(OperationState(target))
            except OperationTransitionError:
                accepted = False
                transitioned = None
            if (target in expected) != accepted:
                raise FormalMethodError(
                    "operation model/code transition conformance mismatch: "
                    f"{source}->{target}"
                )
            if accepted:
                assert transitioned is not None
                if transitioned.state != OperationState(target):
                    raise FormalMethodError(
                        "operation transition returned unexpected target state"
                    )


_PROTOCOL_STORED = ("none", "digest_a", "digest_b")
_PROTOCOL_OUTCOMES = ("none", "accepted", "duplicate", "conflict")


def _protocol_initial(state: FormalState) -> bool:
    values = state.to_mapping()
    return (
        values["seen"] is False
        and values["stored_digest"] == "none"
        and values["last_outcome"] == "none"
    )


def _protocol_transitions(state: FormalState) -> tuple[TransitionCandidate, ...]:
    values = state.to_mapping()
    seen = bool(values["seen"])
    stored = str(values["stored_digest"])
    candidates: list[TransitionCandidate] = []
    for label, digest_name in (
        ("submit_a", "digest_a"),
        ("submit_b", "digest_b"),
    ):
        if not seen:
            outcome = "accepted"
            next_seen = True
            next_stored = digest_name
        elif stored == digest_name:
            outcome = "duplicate"
            next_seen = True
            next_stored = stored
        else:
            outcome = "conflict"
            next_seen = True
            next_stored = stored
        candidates.append(
            TransitionCandidate(
                action=label,
                next_state=_state(
                    seen=next_seen,
                    stored_digest=next_stored,
                    last_outcome=outcome,
                ),
            )
        )
    return tuple(candidates)


def _protocol_storage_invariant(state: FormalState) -> bool:
    seen = bool(state.get("seen"))
    stored = str(state.get("stored_digest"))
    if seen and stored == "none":
        return False
    if not seen and stored != "none":
        return False
    return True


def _protocol_transition_integrity(
    before: FormalState,
    after: FormalState,
    action: str,
) -> bool:
    before_seen = bool(before.get("seen"))
    before_stored = str(before.get("stored_digest"))
    after_seen = bool(after.get("seen"))
    after_stored = str(after.get("stored_digest"))
    outcome = str(after.get("last_outcome"))
    submitted = "digest_a" if action == "submit_a" else "digest_b"

    if not before_seen:
        return (
            after_seen
            and after_stored == submitted
            and outcome == "accepted"
        )
    if after_stored != before_stored:
        return False
    if submitted == before_stored:
        return outcome == "duplicate"
    return outcome == "conflict"


def _protocol_conflict_reachable(state: FormalState) -> bool:
    return state.get("last_outcome") == "conflict"


def protocol_replay_specification() -> FormalSpecification:
    return FormalSpecification(
        spec_id="P0.PROTOCOL.REPLAY",
        title="Canonical protocol replay identity and conflict safety",
        consequence_rank=5,
        ambiguity_rank=4,
        variables=(
            StateVariable("seen", (False, True)),
            StateVariable("stored_digest", _PROTOCOL_STORED),
            StateVariable("last_outcome", _PROTOCOL_OUTCOMES),
        ),
        assumptions=(
            FormalAssumption(
                assumption_id="protocol.single_message_id",
                statement=(
                    "The model tracks one message_id and varies canonical "
                    "content between two distinct digests."
                ),
                falsification_condition=(
                    "Production replay identity is not scoped by message_id."
                ),
            ),
            FormalAssumption(
                assumption_id="protocol.no_eviction",
                statement=(
                    "Replay-guard capacity is large enough that the modeled "
                    "message_id is not evicted during the modeled trace."
                ),
                falsification_condition=(
                    "Capacity eviction occurs before a replay in the trace."
                ),
            ),
        ),
        implementation_bindings=(
            ImplementationBinding.from_object(
                contract_id="ProtocolReplayGuard.accept",
                obj=ProtocolReplayGuard.accept,
                canonical_module_path="skeleton.contracts.protocol",
                canonical_symbol="ProtocolReplayGuard.accept",
            ),
        ),
        obligations=(
            ProofObligation(
                obligation_id="protocol.storage_consistent",
                kind=ObligationKind.INVARIANT,
                statement=(
                    "Tracked replay state is seen exactly when a canonical "
                    "digest is stored."
                ),
                predicate_name="protocol_storage_invariant",
            ),
            ProofObligation(
                obligation_id="protocol.replay_integrity",
                kind=ObligationKind.TRANSITION,
                statement=(
                    "First content is accepted; identical content is a "
                    "duplicate; conflicting content is rejected without "
                    "replacing the stored digest."
                ),
                predicate_name="protocol_transition_integrity",
            ),
            ProofObligation(
                obligation_id="protocol.no_deadlock",
                kind=ObligationKind.DEADLOCK_FREE,
                statement=(
                    "Replay state always accepts another modeled message "
                    "observation as accepted/duplicate/conflict."
                ),
            ),
            ProofObligation(
                obligation_id="protocol.conflict_detectable",
                kind=ObligationKind.REACHABILITY,
                statement=(
                    "A conflicting replay outcome is reachable after a first "
                    "accepted message."
                ),
                predicate_name="protocol_conflict_reachable",
            ),
        ),
        initial_predicate_name="protocol_initial",
        transition_relation_name="protocol_replay_relation",
        max_states=32,
        max_transitions=128,
        max_depth=4,
    )


def protocol_replay_semantics() -> ModelSemantics:
    return ModelSemantics(
        model_id="P0.PROTOCOL.REPLAY.MODEL",
        initial_predicate_name="protocol_initial",
        initial_predicate=_protocol_initial,
        transition_relation_name="protocol_replay_relation",
        transitions=_protocol_transitions,
        predicates={
            "protocol_storage_invariant": _protocol_storage_invariant,
            "protocol_transition_integrity": _protocol_transition_integrity,
            "protocol_conflict_reachable": _protocol_conflict_reachable,
        },
    )


def _protocol_envelope(
    *,
    payload_value: int,
) -> ProtocolEnvelope:
    return ProtocolEnvelope(
        protocol="formal",
        message_id="message.shared",
        kind="formal.test",
        sender="formal.sender",
        recipient="formal.recipient",
        operation_id="operation.formal",
        correlation_id="correlation.formal",
        trace_id="trace.formal",
        idempotency_key="idempotency.formal",
        payload={"value": payload_value},
        retry_class=RetryClass.IDEMPOTENT,
        unknown_outcome_policy=UnknownOutcomePolicy.IDEMPOTENT_REPLAY,
    )


def verify_protocol_replay_conformance() -> None:
    """Compare the P0 replay model outcomes with ProtocolReplayGuard."""

    first = _protocol_envelope(payload_value=1)
    identical = _protocol_envelope(payload_value=1)
    conflicting = _protocol_envelope(payload_value=2)

    guard = ProtocolReplayGuard(max_messages=8)
    if guard.accept(first) is not True:
        raise FormalMethodError(
            "protocol replay conformance: first message was not accepted"
        )
    if guard.accept(identical) is not False:
        raise FormalMethodError(
            "protocol replay conformance: identical replay was not suppressed"
        )
    try:
        guard.accept(conflicting)
    except ProtocolContractError:
        pass
    else:
        raise FormalMethodError(
            "protocol replay conformance: conflicting replay was not rejected"
        )
    if not guard.seen(first.message_id):
        raise FormalMethodError(
            "protocol replay conformance: conflict removed stored identity"
        )


def p0_formal_specifications() -> tuple[FormalSpecification, ...]:
    return (
        operation_lifecycle_specification(),
        protocol_replay_specification(),
    )


def run_p0_formal_models() -> tuple[FormalRunReport, ...]:
    """Run code conformance and both bounded P0 models."""

    verify_operation_transition_conformance()
    verify_protocol_replay_conformance()
    checker = BoundedModelChecker()
    return (
        checker.check(
            operation_lifecycle_specification(),
            operation_lifecycle_semantics(),
        ),
        checker.check(
            protocol_replay_specification(),
            protocol_replay_semantics(),
        ),
    )


__all__ = [
    "operation_lifecycle_semantics",
    "operation_lifecycle_specification",
    "p0_formal_specifications",
    "protocol_replay_semantics",
    "protocol_replay_specification",
    "run_p0_formal_models",
    "verify_operation_transition_conformance",
    "verify_protocol_replay_conformance",
]
