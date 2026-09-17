from dataclasses import replace

from skeleton.jeeves.agent.adaptive_context import AdaptiveContextGovernor
from skeleton.jeeves.agent.context_pipeline import (
    ContextResolution,
    ContextTier,
    LayeredContextResolver,
    ResolutionStage,
)
from skeleton.jeeves.agent.episodic_scaffold import (
    EpisodicScaffoldIndex,
    ScaffoldedMemoryGameIndex,
)
from skeleton.jeeves.agent.lens_fusion import LensFusionEngine, LensSignal
from skeleton.jeeves.agent.memory import MemoryManager, MemoryNamespace
from skeleton.jeeves.agent.memory_game import MemoryGameIndex, MemoryGamePolicy
from skeleton.jeeves.agent.semantic_lenses import LensFamily
from skeleton.jeeves.compiler.ir import (
    BasicBlock,
    Effect,
    FunctionIR,
    IRModule,
    IRType,
    Instruction,
    SSAValue,
    Terminator,
    TerminatorKind,
)
from skeleton.jeeves.compiler.pipeline import PassSemantics
from skeleton.jeeves.compiler.validation_frontier import (
    AssuranceConsensusEngine,
    AssuranceConsensusStatus,
    InternalValidationFactory,
    ValidationEvidence,
    ValidationVerdict,
    ValidatorKind,
)
from skeleton.jeeves.science.lineage import EvidenceGrade
from skeleton.jeeves.science.survivorship import (
    HistoricalEvaluation,
    HistoricalMethod,
    HistoricalSurvivorshipEngine,
    MetricOrientation,
    MetricStandard,
    ScientificFacet,
    SurvivorRole,
    SurvivorshipPolicy,
)


def _module(*, optimized: bool) -> IRModule:
    integer = IRType("i64")
    parameter = SSAValue("x", integer)
    if optimized:
        out = SSAValue("out", integer)
        instructions = (
            Instruction("identity", results=(out,), operands=("x",)),
        )
    else:
        zero = SSAValue("zero", integer)
        out = SSAValue("out", integer)
        instructions = (
            Instruction("const", results=(zero,), attributes={"value": 0}),
            Instruction("add", results=(out,), operands=("x", "zero")),
        )
    function = FunctionIR(
        name="f",
        parameters=(parameter,),
        return_types=(integer,),
        blocks=(
            BasicBlock(
                "entry",
                instructions=instructions,
                terminator=Terminator(TerminatorKind.RETURN, operands=("out",)),
            ),
        ),
        entry="entry",
        declared_effects=frozenset({Effect.PURE}),
    )
    return IRModule((function,))


def test_adaptive_context_honors_explicit_l0_ceiling():
    clock = lambda: 10_000.0
    cards = MemoryGameIndex(clock=clock)
    memory = MemoryManager(clock=clock)
    resolver = LayeredContextResolver(cards=cards, memory=memory)
    governor = AdaptiveContextGovernor(resolver, clock=clock)
    namespace = MemoryNamespace("tenant", "user-a", session_id="s1")

    tier, decisions = governor.choose_max_tier(
        namespace,
        "missing cue",
        hard_max_tier=ContextTier.INDEX_CARD,
    )

    assert tier is ContextTier.INDEX_CARD
    assert decisions == ()


def test_memory_game_is_the_first_and_sufficient_fast_path():
    clock = lambda: 10_000.0
    cards = MemoryGameIndex(
        policy=MemoryGamePolicy(
            minimum_score=0.0,
            minimum_fast_path_coverage=0.0,
            minimum_fast_path_confidence=0.0,
        ),
        clock=clock,
    )
    namespace = MemoryNamespace("tenant", "user-a", session_id="s1")
    cards.capture_interaction(
        namespace,
        "favorite opening is the Sicilian Dragon",
        context_tags=("chess",),
        trust=0.9,
        salience=0.9,
    )
    resolver = LayeredContextResolver(
        cards=cards,
        memory=MemoryManager(clock=clock),
    )
    governor = AdaptiveContextGovernor(resolver, clock=clock)

    result = governor.resolve(
        namespace,
        "favorite opening Sicilian Dragon",
        context_tags=("chess",),
        learn=False,
    )

    assert result.requested_max_tier is ContextTier.INDEX_CARD
    assert result.resolution.fast_path is True
    assert result.resolution.stages[0].tier is ContextTier.INDEX_CARD
    assert all(stage.tier is ContextTier.INDEX_CARD for stage in result.resolution.stages)


def test_adaptive_context_learning_is_namespace_scoped():
    clock = lambda: 10_000.0
    resolver = LayeredContextResolver(
        cards=MemoryGameIndex(clock=clock),
        memory=MemoryManager(clock=clock),
    )
    governor = AdaptiveContextGovernor(resolver, clock=clock)
    left = MemoryNamespace("tenant", "user-a")
    right = MemoryNamespace("tenant", "user-b")
    stage = ResolutionStage(
        tier=ContextTier.SCOPED_MEMORY,
        source="memory_manager",
        queried=True,
        hit_count=3,
        coverage_after=0.6,
        confidence_after=0.7,
        trust_after=0.8,
        marginal_gain=0.15,
        stop_after=False,
        reason="test",
    )
    resolution = ContextResolution(
        query="q",
        items=(),
        stages=(stage,),
        stopped_at=ContextTier.SCOPED_MEMORY,
        fast_path=False,
        final_coverage=0.6,
        final_confidence=0.7,
        final_trust=0.8,
        unresolved_terms=("x",),
        fingerprint="resolution:test",
    )

    governor.observe(left, resolution)

    assert "scoped_memory" in governor.snapshot(left)
    assert governor.snapshot(right) == {}


def _signal(
    signal_id: str,
    p: float,
    family: LensFamily,
    *,
    evidence=(),
    group="g",
):
    return LensSignal(
        signal_id=signal_id,
        lens_key=signal_id,
        family=family,
        probability=p,
        confidence=1.0,
        ambiguity=0.0,
        reliability=1.0,
        epistemic_strength=1.0,
        evidence_ids=tuple(evidence),
        calibration_group=group,
    )


def test_lens_fusion_discounts_redundant_interpretations():
    engine = LensFusionEngine()
    redundant = engine.fuse(
        (
            _signal("film-a", 0.9, LensFamily.FILM, evidence=("e1",), group="film"),
            _signal("film-b", 0.9, LensFamily.FILM, evidence=("e1",), group="film"),
        )
    )
    independent = engine.fuse(
        (
            _signal("film-a", 0.9, LensFamily.FILM, evidence=("e1",), group="film"),
            _signal(
                "game-b",
                0.9,
                LensFamily.GAME,
                evidence=("e2",),
                group="game",
            ),
        )
    )

    assert independent.effective_lens_count > redundant.effective_lens_count
    assert independent.total_effective_weight > redundant.total_effective_weight
    assert any(edge.strength >= 0.8 for edge in redundant.dependencies)


def test_lens_fusion_preserves_counter_reading_conflict_and_abstains():
    result = LensFusionEngine().fuse(
        (
            _signal("pro", 0.9, LensFamily.FILM, group="film"),
            _signal("counter", 0.1, LensFamily.GAME, group="game"),
        )
    )

    assert result.conflict_strength >= 0.9
    assert result.abstain is True
    assert "strong_counter_reading_conflict" in result.abstention_reasons
    assert result.sensitivity_low < result.probability < result.sensitivity_high


def test_survivorship_reconsiders_shadow_method_when_evidence_matures():
    incumbent = HistoricalMethod(
        "old",
        2000,
        "Old",
        ScientificFacet.PREDICTIVE_MODELING,
        "stable baseline",
        EvidenceGrade.REPLICATED,
        complexity_rank=2,
    )
    challenger = HistoricalMethod(
        "new",
        2001,
        "New",
        ScientificFacet.PREDICTIVE_MODELING,
        "candidate improvement",
        EvidenceGrade.EMPIRICAL,
        complexity_rank=3,
    )
    engine = HistoricalSurvivorshipEngine(
        (incumbent, challenger),
        policy=SurvivorshipPolicy(
            minimum_samples=20,
            minimum_replications=2,
            complexity_penalty=0.0,
        ),
    )
    # Both methods issue with information available in 2001 for a 2002 target.
    engine.register_evaluation(
        HistoricalEvaluation(
            "old", "bench", 2002, 2001, 2002, 2002,
            {"accuracy": 0.60}, 100, 3,
        )
    )
    engine.register_evaluation(
        HistoricalEvaluation(
            "new", "bench", 2002, 2001, 2002, 2002,
            {"accuracy": 0.80}, 5, 1,
        )
    )
    # In 2003 replications mature without changing the historical target.
    engine.register_evaluation(
        HistoricalEvaluation(
            "old", "bench", 2003, 2001, 2002, 2002,
            {"accuracy": 0.60}, 120, 4,
        )
    )
    engine.register_evaluation(
        HistoricalEvaluation(
            "new", "bench", 2003, 2001, 2002, 2002,
            {"accuracy": 0.80}, 120, 4,
        )
    )
    standard = MetricStandard(
        "accuracy",
        MetricOrientation.HIGHER,
        weight=1.0,
        introduced_year=1900,
    )

    reports = engine.advance(
        ScientificFacet.PREDICTIVE_MODELING,
        start_year=2000,
        end_year=2003,
        standards=(standard,),
    )

    by_year = {report.year: report for report in reports}
    assert by_year[2002].active_method_id == "old"
    assert SurvivorRole.SHADOW in by_year[2002].survivor_roles["new"]
    assert by_year[2003].active_method_id == "new"
    assert SurvivorRole.BASELINE in by_year[2003].survivor_roles["old"]


def test_validation_consensus_counts_methodological_independence_not_raw_checks():
    source = _module(optimized=False)
    target = _module(optimized=True)
    factory = InternalValidationFactory()
    structural = factory.structural(source, target)
    differential = factory.differential(
        source,
        target,
        cases={"f": ((0,), (1,), (-3,), (99,))},
        semantics=PassSemantics.EXACT,
    )
    duplicate = ValidationEvidence(
        evidence_id="duplicate-diff",
        kind=ValidatorKind.DIFFERENTIAL_EXECUTION,
        checker="second wrapper around same executor",
        checker_version="1",
        independence_group=differential.independence_group,
        source_fingerprint=source.fingerprint,
        target_fingerprint=target.fingerprint,
        property="equivalence",
        verdict=ValidationVerdict.SUPPORTS,
        tested_cases=4,
        coverage=1.0,
    )

    result = AssuranceConsensusEngine().evaluate(
        source,
        target,
        semantics=PassSemantics.EXACT,
        evidence=(structural, differential, duplicate),
    )

    assert result.status is AssuranceConsensusStatus.SINGLE_METHOD
    assert result.accepted is False
    assert len(result.supporting_semantic_groups) == 1


def test_validation_consensus_accepts_independent_semantic_methods_and_refutation_dominates():
    source = _module(optimized=False)
    target = _module(optimized=True)
    factory = InternalValidationFactory()
    structural = factory.structural(source, target)
    differential = factory.differential(
        source,
        target,
        cases={"f": ((0,), (1,), (-3,), (99,))},
        semantics=PassSemantics.EXACT,
    )
    metamorphic = factory.metamorphic(
        source,
        target,
        relation_id="same-result",
        cases={"f": ((0,), (1,), (-3,), (99,))},
        relation=lambda old, new, _args: old == new,
    )
    accepted = AssuranceConsensusEngine().evaluate(
        source,
        target,
        semantics=PassSemantics.EXACT,
        evidence=(structural, differential, metamorphic),
    )
    assert accepted.status is AssuranceConsensusStatus.MULTIMETHOD
    assert accepted.accepted is True

    refutation = ValidationEvidence(
        evidence_id="adversarial-counterexample",
        kind=ValidatorKind.EXTERNAL_SMT,
        checker="external",
        checker_version="1",
        independence_group="external-smt",
        source_fingerprint=source.fingerprint,
        target_fingerprint=target.fingerprint,
        property="equivalence",
        verdict=ValidationVerdict.REFUTES,
        counterexamples=("x = pathological",),
        machine_checked=True,
        artifact_hash="0123456789abcdef",
    )
    rejected = AssuranceConsensusEngine().evaluate(
        source,
        target,
        semantics=PassSemantics.EXACT,
        evidence=(structural, differential, metamorphic, refutation),
    )
    assert rejected.status is AssuranceConsensusStatus.REJECTED
    assert rejected.accepted is False


def test_episodic_scaffold_keeps_repeated_content_as_distinct_positions():
    now = [1_000.0]
    clock = lambda: now[0]
    base = MemoryGameIndex(clock=clock)
    scaffold = EpisodicScaffoldIndex(base, clock=clock)
    namespace = MemoryNamespace("tenant", "user-a", session_id="s1")

    first_card, first = scaffold.capture_interaction(
        namespace, "alpha checkpoint", context_tags=("phase-a",), entity_cues=("engine",)
    )
    now[0] += 10
    _, second = scaffold.capture_interaction(
        namespace, "beta checkpoint", context_tags=("phase-b",), entity_cues=("engine",)
    )
    now[0] += 10
    third_card, third = scaffold.capture_interaction(
        namespace, "alpha checkpoint", context_tags=("phase-a",), entity_cues=("engine",)
    )

    assert first_card.card_id == third_card.card_id
    assert (first.ordinal, second.ordinal, third.ordinal) == (1, 2, 3)
    assert first.episode_id != third.episode_id
    window = scaffold.chronological_window(second.episode_id, radius=1)
    assert [episode.ordinal for episode in window] == [1, 2, 3]


def test_episodic_scaffold_prospection_is_successor_grounded_and_retrieval_only():
    now = [2_000.0]
    clock = lambda: now[0]
    base = MemoryGameIndex(clock=clock)
    scaffold = EpisodicScaffoldIndex(base, clock=clock)
    namespace = MemoryNamespace("tenant", "user-a")

    _, first = scaffold.capture_interaction(namespace, "open project alpha")
    now[0] += 5
    _, second = scaffold.capture_interaction(
        namespace, "run beta verification", context_tags=("verification",)
    )

    probes = scaffold.prospective_probes(namespace, "open project alpha", limit=2)

    assert probes
    assert probes[0].source_episode_id == first.episode_id
    assert probes[0].successor_episode_id == second.episode_id
    assert probes[0].retrieval_only is True
    assert any("beta" == cue for cue in probes[0].cues)


def test_scaffolded_memory_game_remains_layered_context_compatible():
    now = [3_000.0]
    clock = lambda: now[0]
    base = MemoryGameIndex(
        policy=MemoryGamePolicy(
            minimum_score=0.0,
            minimum_fast_path_coverage=0.0,
            minimum_fast_path_confidence=0.0,
        ),
        clock=clock,
    )
    cards = ScaffoldedMemoryGameIndex(base=base, clock=clock)
    namespace = MemoryNamespace("tenant", "user-a", session_id="s1")
    cards.capture_interaction(
        namespace,
        "remember crimson rook",
        context_tags=("board",),
        entity_cues=("rook",),
    )
    resolver = LayeredContextResolver(cards=cards, memory=MemoryManager(clock=clock))

    resolution = resolver.resolve(
        namespace,
        "remember crimson rook",
        context_tags=("board",),
        force_max_tier=ContextTier.ARCHIVE,
    )

    assert resolution.fast_path is True
    assert resolution.stopped_at is ContextTier.INDEX_CARD
    assert resolution.items
