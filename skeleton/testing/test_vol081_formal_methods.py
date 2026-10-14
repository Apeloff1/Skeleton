from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from skeleton.contracts.formal_methods import (
    BoundedModelChecker,
    Counterexample,
    ExplorationStop,
    FormalAssumption,
    FormalMethodError,
    FormalSpecification,
    FormalSpecificationRegistry,
    FormalState,
    ImplementationBinding,
    ModelSemantics,
    ObligationKind,
    ProofObligation,
    ProofStatus,
    StateVariable,
    TransitionCandidate,
)
from skeleton.contracts.formal_targets import (
    operation_lifecycle_semantics,
    operation_lifecycle_specification,
    p0_formal_specifications,
    protocol_replay_semantics,
    protocol_replay_specification,
    run_p0_formal_models,
    verify_operation_transition_conformance,
    verify_protocol_replay_conformance,
)
from skeleton.contracts.operation import OperationEnvelope

ROOT = Path(__file__).resolve().parents[2]


def binding() -> ImplementationBinding:
    return ImplementationBinding.from_object(
        contract_id="OperationEnvelope.transition",
        obj=OperationEnvelope.transition,
        canonical_module_path="skeleton.contracts.operation",
        canonical_symbol="OperationEnvelope.transition",
    )


def assumption() -> FormalAssumption:
    return FormalAssumption(
        assumption_id="test.finite",
        statement="The test model is finite.",
        falsification_condition="The model introduces an unbounded state value.",
    )


def state(x: int) -> FormalState:
    return FormalState.from_mapping({"x": x})


def linear_spec(
    *,
    obligations: tuple[ProofObligation, ...],
    max_states: int = 8,
    max_transitions: int = 16,
    max_depth: int = 4,
    terminal: bool = True,
) -> FormalSpecification:
    return FormalSpecification(
        spec_id="TEST.LINEAR",
        title="Bounded linear formal model",
        consequence_rank=5,
        ambiguity_rank=4,
        variables=(StateVariable("x", (0, 1, 2)),),
        assumptions=(assumption(),),
        implementation_bindings=(binding(),),
        obligations=obligations,
        initial_predicate_name="initial",
        transition_relation_name="linear",
        terminal_predicate_name="terminal" if terminal else None,
        max_states=max_states,
        max_transitions=max_transitions,
        max_depth=max_depth,
    )


def linear_semantics(
    *,
    predicates: dict[str, object],
    terminal: bool = True,
) -> ModelSemantics:
    def initial(current: FormalState) -> bool:
        return current.get("x") == 0

    def transitions(current: FormalState):
        value = int(current.get("x"))
        if value >= 2:
            return ()
        return (
            TransitionCandidate(
                action=f"increment:{value + 1}",
                next_state=state(value + 1),
            ),
        )

    def terminal_predicate(current: FormalState) -> bool:
        return current.get("x") == 2

    return ModelSemantics(
        model_id="TEST.LINEAR.MODEL",
        initial_predicate_name="initial",
        initial_predicate=initial,
        transition_relation_name="linear",
        transitions=transitions,
        predicates=predicates,
        terminal_predicate_name="terminal" if terminal else None,
        terminal_predicate=terminal_predicate if terminal else None,
    )


def standard_obligations() -> tuple[ProofObligation, ...]:
    return (
        ProofObligation(
            obligation_id="test.invariant",
            kind=ObligationKind.INVARIANT,
            statement="x remains in the finite non-negative model.",
            predicate_name="safe",
        ),
        ProofObligation(
            obligation_id="test.transition",
            kind=ObligationKind.TRANSITION,
            statement="Every transition increases x by exactly one.",
            predicate_name="step",
        ),
        ProofObligation(
            obligation_id="test.reach",
            kind=ObligationKind.REACHABILITY,
            statement="x=2 is reachable.",
            predicate_name="target",
        ),
        ProofObligation(
            obligation_id="test.deadlock",
            kind=ObligationKind.DEADLOCK_FREE,
            statement="Every non-terminal state has a successor.",
        ),
    )


def standard_predicates():
    return {
        "safe": lambda current: 0 <= int(current.get("x")) <= 2,
        "step": lambda before, after, action: (
            int(after.get("x")) == int(before.get("x")) + 1
        ),
        "target": lambda current: current.get("x") == 2,
    }


def test_formal_state_is_canonical_across_mapping_order() -> None:
    first = FormalState.from_mapping({"b": True, "a": 1})
    second = FormalState.from_mapping({"a": 1, "b": True})

    assert first == second
    assert first.digest == second.digest
    assert tuple(first.to_mapping()) == ("a", "b")


def test_formal_state_rejects_float_and_duplicate_variable() -> None:
    with pytest.raises(FormalMethodError, match="floating values are forbidden"):
        FormalState.from_mapping({"x": 1.5})

    with pytest.raises(FormalMethodError, match="duplicate state variable"):
        FormalState((("x", 1), ("x", 2)))


def test_state_variable_domain_is_canonical_and_unique() -> None:
    first = StateVariable("x", (2, 0, 1))
    second = StateVariable("x", (0, 1, 2))

    assert first == second
    assert first.domain == (0, 1, 2)
    assert first.digest == second.digest

    with pytest.raises(FormalMethodError, match="duplicate value"):
        StateVariable("x", (1, 1))


def test_assumption_requires_falsification_condition() -> None:
    with pytest.raises(FormalMethodError, match="non-empty bounded text"):
        FormalAssumption(
            assumption_id="bad",
            statement="Assumption.",
            falsification_condition="",
        )


def test_implementation_binding_resolves_and_verifies_canonical_source() -> None:
    item = binding()

    assert item.module_path == "skeleton.contracts.operation"
    assert item.symbol == "OperationEnvelope.transition"
    assert item.resolve() is OperationEnvelope.transition
    item.verify()


def test_implementation_binding_detects_source_digest_drift() -> None:
    forged = replace(binding(), source_sha256="0" * 64)

    with pytest.raises(FormalMethodError, match="binding drift"):
        forged.verify()


def test_formal_spec_selection_score_prioritizes_consequence_and_ambiguity() -> None:
    low = FormalSpecification(
        spec_id="SPEC.LOW",
        title="Low consequence",
        consequence_rank=1,
        ambiguity_rank=1,
        variables=(StateVariable("x", (0, 1)),),
        assumptions=(assumption(),),
        implementation_bindings=(binding(),),
        obligations=(
            ProofObligation(
                obligation_id="low.safe",
                kind=ObligationKind.INVARIANT,
                statement="Always safe.",
                predicate_name="safe",
            ),
        ),
        initial_predicate_name="initial",
        transition_relation_name="transition",
    )
    high = replace(
        low,
        spec_id="SPEC.HIGH",
        consequence_rank=5,
        ambiguity_rank=5,
    )

    assert low.selection_score == 1
    assert high.selection_score == 25


def test_spec_rejects_duplicate_contract_binding() -> None:
    with pytest.raises(FormalMethodError, match="duplicate implementation"):
        FormalSpecification(
            spec_id="SPEC.DUP.BINDING",
            title="Duplicate binding",
            consequence_rank=5,
            ambiguity_rank=5,
            variables=(StateVariable("x", (0, 1)),),
            assumptions=(assumption(),),
            implementation_bindings=(binding(), binding()),
            obligations=(
                ProofObligation(
                    obligation_id="safe",
                    kind=ObligationKind.INVARIANT,
                    statement="safe",
                    predicate_name="safe",
                ),
            ),
            initial_predicate_name="initial",
            transition_relation_name="transition",
        )


def test_spec_rejects_duplicate_obligation_identity() -> None:
    obligation = ProofObligation(
        obligation_id="duplicate",
        kind=ObligationKind.INVARIANT,
        statement="safe",
        predicate_name="safe",
    )

    with pytest.raises(FormalMethodError, match="duplicate proof-obligation"):
        FormalSpecification(
            spec_id="SPEC.DUP.OBLIGATION",
            title="Duplicate obligation",
            consequence_rank=5,
            ambiguity_rank=5,
            variables=(StateVariable("x", (0, 1)),),
            assumptions=(assumption(),),
            implementation_bindings=(binding(),),
            obligations=(obligation, obligation),
            initial_predicate_name="initial",
            transition_relation_name="transition",
        )


def test_deadlock_obligation_cannot_define_predicate() -> None:
    with pytest.raises(FormalMethodError, match="must not define predicate"):
        ProofObligation(
            obligation_id="deadlock",
            kind=ObligationKind.DEADLOCK_FREE,
            statement="No deadlocks.",
            predicate_name="deadlock",
        )


def test_non_deadlock_obligation_requires_predicate() -> None:
    with pytest.raises(FormalMethodError, match="requires predicate_name"):
        ProofObligation(
            obligation_id="safe",
            kind=ObligationKind.INVARIANT,
            statement="Safe.",
        )


def test_registry_is_idempotent_and_prioritized() -> None:
    low = FormalSpecification(
        spec_id="SPEC.REG.LOW",
        title="Low priority",
        consequence_rank=1,
        ambiguity_rank=1,
        variables=(StateVariable("x", (0, 1)),),
        assumptions=(assumption(),),
        implementation_bindings=(binding(),),
        obligations=(
            ProofObligation(
                obligation_id="low",
                kind=ObligationKind.INVARIANT,
                statement="Safe.",
                predicate_name="safe",
            ),
        ),
        initial_predicate_name="initial",
        transition_relation_name="transition",
    )
    high = replace(
        low,
        spec_id="SPEC.REG.HIGH",
        consequence_rank=5,
        ambiguity_rank=5,
    )
    registry = FormalSpecificationRegistry()

    assert registry.register(low) is low
    assert registry.register(low) is low
    registry.register(high)

    assert registry.get("SPEC.REG.HIGH") is high
    assert registry.prioritized() == (high, low)
    assert registry.for_contract("OperationEnvelope.transition") == (
        high,
        low,
    )
    assert registry.digest


def test_registry_rejects_spec_identity_collision() -> None:
    first = linear_spec(obligations=standard_obligations())
    second = replace(first, title="Different content")
    registry = FormalSpecificationRegistry()
    registry.register(first)

    with pytest.raises(FormalMethodError, match="identity collision"):
        registry.register(second)


def test_standard_linear_model_proves_all_obligations_within_model() -> None:
    report = BoundedModelChecker().check(
        linear_spec(obligations=standard_obligations()),
        linear_semantics(predicates=standard_predicates()),
    )

    assert report.stop_reason is ExplorationStop.COMPLETE
    assert report.explored_states == 3
    assert report.explored_transitions == 2
    assert report.maximum_depth_reached == 2
    assert report.all_obligations_proved_within_model is True
    assert report.universally_proves_implementation_correct is False
    assert all(
        result.status is ProofStatus.PROVED_WITHIN_MODEL
        for result in report.results
    )
    assert "scoped" in report.scope_statement.lower()


def test_invariant_failure_returns_replayable_counterexample() -> None:
    predicates = standard_predicates()
    predicates["safe"] = lambda current: int(current.get("x")) < 2
    spec = linear_spec(obligations=standard_obligations())
    semantics = linear_semantics(predicates=predicates)
    checker = BoundedModelChecker()

    report = checker.check(spec, semantics)
    result = next(
        item for item in report.results
        if item.obligation_id == "test.invariant"
    )

    assert result.status is ProofStatus.REFUTED
    assert result.counterexample is not None
    assert result.counterexample.failing_state.get("x") == 2
    assert len(result.counterexample.trace) == 2
    checker.replay_counterexample(
        spec,
        semantics,
        result.counterexample,
    )


def test_counterexample_replay_detects_model_drift() -> None:
    predicates = standard_predicates()
    predicates["safe"] = lambda current: int(current.get("x")) < 2
    spec = linear_spec(obligations=standard_obligations())
    original = linear_semantics(predicates=predicates)
    checker = BoundedModelChecker()
    report = checker.check(spec, original)
    counterexample = next(
        item.counterexample for item in report.results
        if item.obligation_id == "test.invariant"
    )
    assert counterexample is not None

    def initial(current: FormalState) -> bool:
        return current.get("x") == 0

    def drifted_transitions(current: FormalState):
        if current.get("x") == 0:
            return (
                TransitionCandidate(
                    action="increment:1",
                    next_state=state(1),
                ),
            )
        return ()

    drifted = ModelSemantics(
        model_id="DRIFTED",
        initial_predicate_name="initial",
        initial_predicate=initial,
        transition_relation_name="linear",
        transitions=drifted_transitions,
        predicates=predicates,
        terminal_predicate_name="terminal",
        terminal_predicate=lambda current: current.get("x") == 2,
    )

    with pytest.raises(FormalMethodError, match="no longer replays uniquely"):
        checker.replay_counterexample(
            spec,
            drifted,
            counterexample,
        )


def test_transition_failure_returns_edge_counterexample() -> None:
    predicates = standard_predicates()
    predicates["step"] = lambda before, after, action: (
        int(after.get("x")) == 1
    )
    report = BoundedModelChecker().check(
        linear_spec(obligations=standard_obligations()),
        linear_semantics(predicates=predicates),
    )
    result = next(
        item for item in report.results
        if item.obligation_id == "test.transition"
    )

    assert result.status is ProofStatus.REFUTED
    assert result.counterexample is not None
    assert result.counterexample.failing_state.get("x") == 2
    assert result.counterexample.trace[-1].action == "increment:2"


def test_deadlock_failure_is_counterexample_when_state_is_nonterminal() -> None:
    obligation = ProofObligation(
        obligation_id="deadlock",
        kind=ObligationKind.DEADLOCK_FREE,
        statement="No deadlocks.",
    )
    spec = FormalSpecification(
        spec_id="TEST.DEADLOCK",
        title="Deadlock model",
        consequence_rank=5,
        ambiguity_rank=5,
        variables=(StateVariable("x", (0, 1)),),
        assumptions=(assumption(),),
        implementation_bindings=(binding(),),
        obligations=(obligation,),
        initial_predicate_name="initial",
        transition_relation_name="transition",
        max_states=4,
        max_transitions=4,
        max_depth=4,
    )

    semantics = ModelSemantics(
        model_id="TEST.DEADLOCK.MODEL",
        initial_predicate_name="initial",
        initial_predicate=lambda current: current.get("x") == 0,
        transition_relation_name="transition",
        transitions=lambda current: (
            (
                TransitionCandidate(
                    action="to:1",
                    next_state=FormalState.from_mapping({"x": 1}),
                ),
            )
            if current.get("x") == 0
            else ()
        ),
        predicates={},
    )

    report = BoundedModelChecker().check(spec, semantics)
    result = report.results[0]

    assert result.status is ProofStatus.REFUTED
    assert result.counterexample is not None
    assert result.counterexample.failing_state.get("x") == 1


def test_unreachable_target_is_refuted_only_after_complete_exploration() -> None:
    obligation = ProofObligation(
        obligation_id="reach",
        kind=ObligationKind.REACHABILITY,
        statement="x=2 is reachable.",
        predicate_name="target",
    )
    spec = linear_spec(obligations=(obligation,))
    semantics = linear_semantics(
        predicates={"target": lambda current: False}
    )

    report = BoundedModelChecker().check(spec, semantics)

    assert report.stop_reason is ExplorationStop.COMPLETE
    assert report.results[0].status is ProofStatus.REFUTED
    assert report.results[0].counterexample is not None


def test_reachability_witness_can_prove_before_full_model_completion() -> None:
    obligation = ProofObligation(
        obligation_id="reach",
        kind=ObligationKind.REACHABILITY,
        statement="x=1 is reachable.",
        predicate_name="target",
    )
    spec = linear_spec(
        obligations=(obligation,),
        max_depth=1,
    )
    semantics = linear_semantics(
        predicates={"target": lambda current: current.get("x") == 1}
    )

    report = BoundedModelChecker().check(spec, semantics)

    assert report.stop_reason is ExplorationStop.DEPTH_BOUND
    assert report.results[0].status is ProofStatus.PROVED_WITHIN_MODEL
    assert report.results[0].witness_state_digest is not None


def test_depth_bound_makes_unresolved_safety_proof_inconclusive() -> None:
    obligation = ProofObligation(
        obligation_id="safe",
        kind=ObligationKind.INVARIANT,
        statement="Always safe.",
        predicate_name="safe",
    )
    spec = linear_spec(
        obligations=(obligation,),
        max_depth=1,
    )
    semantics = linear_semantics(
        predicates={"safe": lambda current: True}
    )

    report = BoundedModelChecker().check(spec, semantics)

    assert report.stop_reason is ExplorationStop.DEPTH_BOUND
    assert report.results[0].status is ProofStatus.INCONCLUSIVE_BOUND


def test_state_bound_makes_unresolved_proof_inconclusive() -> None:
    obligation = ProofObligation(
        obligation_id="safe",
        kind=ObligationKind.INVARIANT,
        statement="Always safe.",
        predicate_name="safe",
    )
    spec = linear_spec(
        obligations=(obligation,),
        max_states=1,
    )
    semantics = linear_semantics(
        predicates={"safe": lambda current: True}
    )

    report = BoundedModelChecker().check(spec, semantics)

    assert report.stop_reason is ExplorationStop.STATE_BOUND
    assert report.explored_states == 1
    assert report.results[0].status is ProofStatus.INCONCLUSIVE_BOUND


def test_transition_bound_makes_unresolved_proof_inconclusive() -> None:
    obligation = ProofObligation(
        obligation_id="safe",
        kind=ObligationKind.INVARIANT,
        statement="Always safe.",
        predicate_name="safe",
    )
    spec = linear_spec(
        obligations=(obligation,),
        max_transitions=1,
    )
    semantics = linear_semantics(
        predicates={"safe": lambda current: True}
    )

    report = BoundedModelChecker().check(spec, semantics)

    assert report.stop_reason is ExplorationStop.TRANSITION_BOUND
    assert report.explored_transitions == 1
    assert report.results[0].status is ProofStatus.INCONCLUSIVE_BOUND


def test_checker_rejects_semantics_name_mismatch() -> None:
    spec = linear_spec(obligations=standard_obligations())
    semantics = ModelSemantics(
        model_id="BAD.NAMES",
        initial_predicate_name="wrong",
        initial_predicate=lambda current: True,
        transition_relation_name="linear",
        transitions=lambda current: (),
        predicates=standard_predicates(),
        terminal_predicate_name="terminal",
        terminal_predicate=lambda current: True,
    )

    with pytest.raises(FormalMethodError, match="initial predicate name"):
        BoundedModelChecker().check(spec, semantics)


def test_checker_rejects_missing_obligation_predicate() -> None:
    spec = linear_spec(obligations=standard_obligations())
    predicates = standard_predicates()
    predicates.pop("safe")
    semantics = linear_semantics(predicates=predicates)

    with pytest.raises(FormalMethodError, match="missing predicate safe"):
        BoundedModelChecker().check(spec, semantics)


def test_checker_rejects_model_without_initial_state() -> None:
    spec = linear_spec(
        obligations=(
            ProofObligation(
                obligation_id="safe",
                kind=ObligationKind.INVARIANT,
                statement="Safe.",
                predicate_name="safe",
            ),
        )
    )
    semantics = ModelSemantics(
        model_id="NO.INITIAL",
        initial_predicate_name="initial",
        initial_predicate=lambda current: False,
        transition_relation_name="linear",
        transitions=lambda current: (),
        predicates={"safe": lambda current: True},
        terminal_predicate_name="terminal",
        terminal_predicate=lambda current: True,
    )

    with pytest.raises(FormalMethodError, match="no state satisfying"):
        BoundedModelChecker().check(spec, semantics)


def test_checker_rejects_out_of_domain_transition_state() -> None:
    spec = linear_spec(
        obligations=(
            ProofObligation(
                obligation_id="safe",
                kind=ObligationKind.INVARIANT,
                statement="Safe.",
                predicate_name="safe",
            ),
        )
    )
    semantics = ModelSemantics(
        model_id="OUT.OF.DOMAIN",
        initial_predicate_name="initial",
        initial_predicate=lambda current: current.get("x") == 0,
        transition_relation_name="linear",
        transitions=lambda current: (
            TransitionCandidate(
                action="escape",
                next_state=FormalState.from_mapping({"x": 99}),
            ),
        ),
        predicates={"safe": lambda current: True},
        terminal_predicate_name="terminal",
        terminal_predicate=lambda current: False,
    )

    with pytest.raises(FormalMethodError, match="escapes declared domain"):
        BoundedModelChecker().check(spec, semantics)


def test_checker_rejects_duplicate_transition() -> None:
    spec = linear_spec(
        obligations=(
            ProofObligation(
                obligation_id="safe",
                kind=ObligationKind.INVARIANT,
                statement="Safe.",
                predicate_name="safe",
            ),
        )
    )
    candidate = TransitionCandidate(
        action="same",
        next_state=state(1),
    )
    semantics = ModelSemantics(
        model_id="DUP.TRANSITION",
        initial_predicate_name="initial",
        initial_predicate=lambda current: current.get("x") == 0,
        transition_relation_name="linear",
        transitions=lambda current: (candidate, candidate),
        predicates={"safe": lambda current: True},
        terminal_predicate_name="terminal",
        terminal_predicate=lambda current: False,
    )

    with pytest.raises(FormalMethodError, match="duplicate transition"):
        BoundedModelChecker().check(spec, semantics)


def test_checker_rejects_generator_transition_relation() -> None:
    spec = linear_spec(
        obligations=(
            ProofObligation(
                obligation_id="safe",
                kind=ObligationKind.INVARIANT,
                statement="Safe.",
                predicate_name="safe",
            ),
        )
    )

    def transitions(current):
        return (
            candidate
            for candidate in (
                TransitionCandidate(
                    action="one",
                    next_state=state(1),
                ),
            )
        )

    semantics = ModelSemantics(
        model_id="GENERATOR.TRANSITION",
        initial_predicate_name="initial",
        initial_predicate=lambda current: current.get("x") == 0,
        transition_relation_name="linear",
        transitions=transitions,
        predicates={"safe": lambda current: True},
        terminal_predicate_name="terminal",
        terminal_predicate=lambda current: False,
    )

    with pytest.raises(FormalMethodError, match="finite sequence"):
        BoundedModelChecker().check(spec, semantics)


def test_checker_rejects_non_boolean_predicate() -> None:
    spec = linear_spec(
        obligations=(
            ProofObligation(
                obligation_id="safe",
                kind=ObligationKind.INVARIANT,
                statement="Safe.",
                predicate_name="safe",
            ),
        )
    )
    semantics = linear_semantics(
        predicates={"safe": lambda current: 1}
    )

    with pytest.raises(FormalMethodError, match="must return bool"):
        BoundedModelChecker().check(spec, semantics)


def test_checker_wraps_predicate_exception_as_formal_error() -> None:
    spec = linear_spec(
        obligations=(
            ProofObligation(
                obligation_id="safe",
                kind=ObligationKind.INVARIANT,
                statement="Safe.",
                predicate_name="safe",
            ),
        )
    )

    def explode(current):
        raise RuntimeError("boom")

    semantics = linear_semantics(predicates={"safe": explode})

    with pytest.raises(FormalMethodError, match="raised an exception"):
        BoundedModelChecker().check(spec, semantics)


def test_checker_can_skip_binding_verification_for_isolated_model_work() -> None:
    forged = replace(binding(), source_sha256="0" * 64)
    spec = replace(
        linear_spec(obligations=standard_obligations()),
        implementation_bindings=(forged,),
    )

    report = BoundedModelChecker().check(
        spec,
        linear_semantics(predicates=standard_predicates()),
        verify_implementation_bindings=False,
    )

    assert report.all_obligations_proved_within_model


def test_checker_fails_closed_on_binding_drift_by_default() -> None:
    forged = replace(binding(), source_sha256="0" * 64)
    spec = replace(
        linear_spec(obligations=standard_obligations()),
        implementation_bindings=(forged,),
    )

    with pytest.raises(FormalMethodError, match="binding drift"):
        BoundedModelChecker().check(
            spec,
            linear_semantics(predicates=standard_predicates()),
        )


def test_operation_p0_spec_binds_canonical_implementation() -> None:
    spec = operation_lifecycle_specification()

    assert spec.spec_id == "P0.OPERATION.LIFECYCLE"
    assert spec.selection_score == 20
    assert spec.theoretical_state_count == 52
    assert spec.implementation_bindings[0].module_path == (
        "skeleton.contracts.operation"
    )
    assert spec.implementation_bindings[0].symbol == (
        "OperationEnvelope.transition"
    )


def test_protocol_p0_spec_binds_canonical_implementation() -> None:
    spec = protocol_replay_specification()

    assert spec.spec_id == "P0.PROTOCOL.REPLAY"
    assert spec.selection_score == 20
    assert spec.theoretical_state_count == 24
    assert spec.implementation_bindings[0].module_path == (
        "skeleton.contracts.protocol"
    )
    assert spec.implementation_bindings[0].symbol == (
        "ProtocolReplayGuard.accept"
    )


def test_operation_model_matches_production_transition_contract() -> None:
    verify_operation_transition_conformance()


def test_protocol_model_matches_production_replay_contract() -> None:
    verify_protocol_replay_conformance()


def test_operation_p0_model_proves_declared_obligations() -> None:
    report = BoundedModelChecker().check(
        operation_lifecycle_specification(),
        operation_lifecycle_semantics(),
    )

    assert report.stop_reason is ExplorationStop.COMPLETE
    assert report.all_obligations_proved_within_model
    assert report.universally_proves_implementation_correct is False
    assert {
        result.obligation_id for result in report.results
    } == {
        "operation.authority_order",
        "operation.history_monotonic",
        "operation.no_nonterminal_deadlock",
        "operation.completion_reachable",
    }


def test_protocol_p0_model_proves_declared_obligations() -> None:
    report = BoundedModelChecker().check(
        protocol_replay_specification(),
        protocol_replay_semantics(),
    )

    assert report.stop_reason is ExplorationStop.COMPLETE
    assert report.all_obligations_proved_within_model
    assert {
        result.obligation_id for result in report.results
    } == {
        "protocol.storage_consistent",
        "protocol.replay_integrity",
        "protocol.no_deadlock",
        "protocol.conflict_detectable",
    }


def test_p0_catalog_is_deterministic_and_complete() -> None:
    first = p0_formal_specifications()
    second = p0_formal_specifications()

    assert first == second
    assert tuple(item.spec_id for item in first) == (
        "P0.OPERATION.LIFECYCLE",
        "P0.PROTOCOL.REPLAY",
    )
    assert tuple(item.digest for item in first) == tuple(
        item.digest for item in second
    )


def test_p0_runner_executes_conformance_and_models() -> None:
    reports = run_p0_formal_models()

    assert len(reports) == 2
    assert all(
        report.all_obligations_proved_within_model
        for report in reports
    )
    assert all(
        report.universally_proves_implementation_correct is False
        for report in reports
    )


def test_canonical_and_ai_formal_runtime_are_byte_identical() -> None:
    assert (
        ROOT / "skeleton/contracts/formal_methods.py"
    ).read_bytes() == (
        ROOT / "skeleton/ai/runtime/contracts/formal_methods.py"
    ).read_bytes()


def test_canonical_and_ai_p0_targets_are_byte_identical() -> None:
    assert (
        ROOT / "skeleton/contracts/formal_targets.py"
    ).read_bytes() == (
        ROOT / "skeleton/ai/runtime/contracts/formal_targets.py"
    ).read_bytes()


def test_canonical_and_ai_contract_exports_are_byte_identical() -> None:
    assert (
        ROOT / "skeleton/contracts/__init__.py"
    ).read_bytes() == (
        ROOT / "skeleton/ai/runtime/contracts/__init__.py"
    ).read_bytes()


def test_spec_rejects_cartesian_state_space_above_hard_bound() -> None:
    with pytest.raises(
        FormalMethodError,
        match="Cartesian state space exceeds hard enumeration bound",
    ):
        FormalSpecification(
            spec_id="SPEC.TOO.LARGE",
            title="State explosion",
            consequence_rank=5,
            ambiguity_rank=5,
            variables=(
                StateVariable("a", tuple(range(1001))),
                StateVariable("b", tuple(range(1001))),
            ),
            assumptions=(assumption(),),
            implementation_bindings=(binding(),),
            obligations=(
                ProofObligation(
                    obligation_id="safe",
                    kind=ObligationKind.INVARIANT,
                    statement="Safe.",
                    predicate_name="safe",
                ),
            ),
            initial_predicate_name="initial",
            transition_relation_name="transition",
        )

def test_aggregate_proof_claim_fails_closed_when_report_is_incomplete() -> None:
    report = BoundedModelChecker().check(
        linear_spec(obligations=standard_obligations()),
        linear_semantics(predicates=standard_predicates()),
    )
    assert report.all_obligations_proved_within_model is True

    forged = replace(
        report,
        stop_reason=ExplorationStop.DEPTH_BOUND,
    )
    assert all(
        result.status is ProofStatus.PROVED_WITHIN_MODEL
        for result in forged.results
    )
    assert forged.all_obligations_proved_within_model is False
