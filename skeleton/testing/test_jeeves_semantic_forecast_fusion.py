from __future__ import annotations

from skeleton.jeeves.agent.context_pipeline import LayeredContextResolver, ResolutionPolicy
from skeleton.jeeves.agent.memory import MemoryManager, MemoryNamespace
from skeleton.jeeves.agent.memory_game import MemoryGameIndex, MemoryGamePolicy
from skeleton.jeeves.agent.nuance_runtime import ScientificNuanceRuntime
from skeleton.jeeves.agent.relational_memory import RelationalMemoryIndex
from skeleton.jeeves.agent.semantic_frontier import FrontierSemanticRegistry
from skeleton.jeeves.agent.semantic_fusion_runtime import SemanticForecastFusionEngine
from skeleton.jeeves.agent.semantic_lenses import LensFamily, SemanticFinding
from skeleton.jeeves.agent.semantic_prediction import SemanticForecast


def _forecast(
    forecast_id: str,
    *,
    proposition: str,
    lens_key: str,
    observation_id: str,
    probability: float = 0.80,
    calibration_group: str | None = None,
) -> SemanticForecast:
    return SemanticForecast(
        forecast_id=forecast_id,
        proposition=proposition,
        probability=probability,
        created_at=1.0,
        horizon="next-relevant-observation",
        source_lens_keys=(lens_key,),
        observation_ids=(observation_id,),
        falsifiers=("observe a relevant failure",),
        calibration_group=calibration_group or f"semantic:{lens_key}",
        ambiguity=0.05,
        epistemic_strength=0.95,
    )


def _runtime() -> tuple[MemoryNamespace, ScientificNuanceRuntime]:
    namespace = MemoryNamespace("tenant", "user", "workspace", "session")
    cards = MemoryGameIndex(policy=MemoryGamePolicy(minimum_score=0.0))
    resolver = LayeredContextResolver(
        cards=cards,
        relations=RelationalMemoryIndex(cards),
        memory=MemoryManager(),
        policy=ResolutionPolicy(
            minimum_item_score=0.0,
            stop_coverage=1.0,
            stop_confidence=1.0,
            stop_trust=1.0,
        ),
    )
    return namespace, ScientificNuanceRuntime(resolver)


def test_fusion_groups_only_textually_identical_targets() -> None:
    engine = SemanticForecastFusionEngine(FrontierSemanticRegistry())
    snapshot = engine.fuse(
        (
            _forecast(
                "forecast:a",
                proposition="The event recurs.",
                lens_key="montage_collision",
                observation_id="obs:a",
            ),
            _forecast(
                "forecast:b",
                proposition="  the   event recurs. ",
                lens_key="unreliable_narrator",
                observation_id="obs:b",
                probability=0.76,
            ),
        )
    )

    assert len(snapshot.fusions) == 1
    fusion = snapshot.fusions[0]
    assert fusion.forecast_ids == ("forecast:a", "forecast:b")
    assert set(fusion.lens_keys) == {
        "montage_collision",
        "unreliable_narrator",
    }
    assert fusion.result.effective_lens_count > 1.0
    assert fusion.result.abstain is False
    assert snapshot.excluded_forecast_ids == ()


def test_fusion_never_pools_different_propositions() -> None:
    engine = SemanticForecastFusionEngine(FrontierSemanticRegistry())
    snapshot = engine.fuse(
        (
            _forecast(
                "forecast:a",
                proposition="The event recurs.",
                lens_key="montage_collision",
                observation_id="obs:a",
            ),
            _forecast(
                "forecast:b",
                proposition="The narrator is contradicted.",
                lens_key="unreliable_narrator",
                observation_id="obs:b",
            ),
        )
    )

    assert len(snapshot.fusions) == 2
    assert all(len(item.forecast_ids) == 1 for item in snapshot.fusions)
    assert all(item.result.abstain for item in snapshot.fusions)


def test_multi_lens_interaction_forecast_is_not_assigned_a_fake_family() -> None:
    engine = SemanticForecastFusionEngine(FrontierSemanticRegistry())
    forecast = SemanticForecast(
        forecast_id="forecast:interaction",
        proposition="The combined reading predicts a shift.",
        probability=0.72,
        created_at=1.0,
        horizon="next-discriminating-observation",
        source_lens_keys=("montage_collision", "unreliable_narrator"),
        observation_ids=("obs:a", "obs:b"),
        ambiguity=0.20,
        epistemic_strength=0.80,
    )

    snapshot = engine.fuse((forecast,))

    assert snapshot.fusions == ()
    assert snapshot.excluded_forecast_ids == ("forecast:interaction",)


def test_shared_observations_can_force_conservative_fusion_abstention() -> None:
    engine = SemanticForecastFusionEngine(FrontierSemanticRegistry())
    snapshot = engine.fuse(
        (
            _forecast(
                "forecast:a",
                proposition="The event recurs.",
                lens_key="montage_collision",
                observation_id="obs:shared",
            ),
            _forecast(
                "forecast:b",
                proposition="The event recurs.",
                lens_key="unreliable_narrator",
                observation_id="obs:shared",
                probability=0.78,
            ),
        )
    )

    fusion = snapshot.fusions[0]
    assert fusion.result.dependencies
    assert fusion.result.abstain is True
    assert (
        "insufficient_effective_weight" in fusion.result.abstention_reasons
        or "insufficient_independent_lenses" in fusion.result.abstention_reasons
    )


def test_nuance_update_records_governed_forecast_fusion() -> None:
    namespace, runtime = _runtime()
    runtime.prepare(
        namespace,
        "Earlier a narrator described a neutral face as calm.",
    )
    frame = runtime.prepare(
        namespace,
        "A montage contrast places the face beside a coffin and challenges the narrator.",
        requested_lenses=("montage_collision", "unreliable_narrator"),
        capture_interaction=False,
    )
    observation_ids = tuple(item.observation_id for item in frame.observations[:2])
    shared_prediction = "A later independent observation will preserve the contrast signal."
    findings = (
        SemanticFinding(
            finding_id="finding:a",
            lens_key="montage_collision",
            family=LensFamily.FILM,
            observation_ids=observation_ids,
            interpretation="The juxtaposition supports a contrast reading.",
            prediction=shared_prediction,
            confidence=0.88,
            ambiguity=0.16,
            novelty=0.70,
        ),
        SemanticFinding(
            finding_id="finding:b",
            lens_key="unreliable_narrator",
            family=LensFamily.LITERATURE,
            observation_ids=observation_ids,
            interpretation="Independent framing challenges the narrated claim.",
            prediction=shared_prediction,
            confidence=0.84,
            ambiguity=0.18,
            novelty=0.65,
        ),
    )

    update = runtime.register_findings(frame, findings, sequence=4)

    assert update.forecast_fusion is not None
    assert update.forecast_fusion.fusions
    fusion = next(
        item
        for item in update.forecast_fusion.fusions
        if len(item.forecast_ids) == 2
    )
    assert fusion.result.abstain is True
    summary = runtime.lens_science_summary()
    assert summary["forecast_fusion_snapshot_count"] == 1
    assert summary["forecast_fusion_group_count"] >= 1
    assert summary["forecast_fusion_abstention_count"] >= 1
    assert (
        summary["invariants"]["forecast_fusion_requires_textually_identical_targets"]
        is True
    )
