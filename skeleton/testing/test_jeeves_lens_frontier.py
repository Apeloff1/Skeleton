from __future__ import annotations

from skeleton.jeeves.agent.lens_governance import LensScienceRegistry, ScientificGrade
from skeleton.jeeves.agent.lens_system import (
    LensFamily,
    SemanticLensRouter,
    default_lenses,
)


def test_frontier_lens_catalog_has_deep_perpendicular_coverage() -> None:
    definitions = default_lenses()
    ids = [lens.lens_id for lens in definitions]
    assert len(ids) == len(set(ids))

    by_family = {
        family: [lens for lens in definitions if lens.family is family]
        for family in LensFamily
    }
    assert len(by_family[LensFamily.PROBABILITY]) >= 30
    assert len(by_family[LensFamily.SEMIOTIC]) >= 10
    assert len(by_family[LensFamily.CINEMA]) >= 30
    assert len(by_family[LensFamily.LITERARY]) >= 30
    assert len(by_family[LensFamily.LUDIC]) >= 30

    required = {
        "martingale_evalue",
        "multicalibration",
        "extreme_value_tail",
        "semiotic_square",
        "syntagm_paradigm",
        "kuleshov_juxtaposition",
        "split_screen_parallelism",
        "suture",
        "fabula_syuzhet",
        "metalepsis",
        "mise_en_abyme",
        "exploitability",
        "regret_minimization",
        "signaling_game",
        "environmental_storytelling",
        "player_modeling",
    }
    assert required.issubset(set(ids))


def test_juxtaposition_query_routes_across_semantic_movie_literary_and_game_axes() -> None:
    router = SemanticLensRouter()
    bundle = router.route(
        (
            "Use juxtaposition and a semiotic square. Compare a split screen graphic rhyme, "
            "fabula syuzhet and mise en abyme, then test exploitability and a signaling game."
        ),
        limit=32,
    )
    selected = set(bundle.ids())
    assert "semiotic_square" in selected
    assert "split_screen_parallelism" in selected
    assert "fabula_syuzhet" in selected
    assert "exploitability" in selected
    assert {
        LensFamily.SEMIOTIC,
        LensFamily.CINEMA,
        LensFamily.LITERARY,
        LensFamily.LUDIC,
    }.issubset(set(bundle.families))


def test_rare_interpretive_lenses_never_gain_factual_or_causal_authority_by_default() -> None:
    router = SemanticLensRouter()
    bundle = router.route("mise en abyme nested mirror narrative", limit=24)
    activation = next(item for item in bundle.activations if item.lens.lens_id == "mise_en_abyme")

    decision = LensScienceRegistry().assess(activation)

    assert decision.grade is ScientificGrade.INTERPRETIVE
    assert decision.factual_assertion_authorized is False
    assert decision.causal_assertion_authorized is False
    assert decision.decision_feature_authorized is False
    assert 0.0 <= decision.predictive_weight <= 1.0
