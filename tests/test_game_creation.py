from dataclasses import replace

from skeleton.context import intake
from skeleton.forge.universal import Forge
from skeleton.pipelines.game_creation import GameCreationPlanner, GameSystem
from skeleton.pipelines.gameforge import GameForge


def test_planner_turns_sparse_intake_into_complete_creation_contract() -> None:
    answers = {
        "genre": "roguelite",
        "scope": "prototype",
        "perspective": "isometric",
        "concept": "descend into a procedural clockwork vault and escape with relics",
        "death": "the_raid",
        "era_explicit": "extraction_now",
    }
    result = GameCreationPlanner().create(
        intake=intake(answers),
        answers=answers,
        title="Clockwork Descent",
    )

    assert result.assessment.ok
    assert result.plan.genre == "roguelike"
    assert result.plan.scope == "prototype"
    assert len(result.plan.core_loop) >= 4
    assert len(result.plan.player_verbs) >= 3
    assert len(result.plan.playtests) >= 4
    assert result.plan.content_budget["locations"] == 1
    assert result.plan.to_build_plan()["game_creation"]["title"] == "Clockwork Descent"


def test_genre_is_derived_without_nonexistent_intake_genre_attribute() -> None:
    raw = {"combat": "instantly", "era_explicit": "boomer_shooter"}
    parsed = intake(raw)

    assert not hasattr(parsed, "genre")
    assert GameCreationPlanner().infer_genre(raw, parsed.era) == "shooter"


def test_assessment_detects_dangling_dependencies_and_cycles() -> None:
    planner = GameCreationPlanner()
    result = planner.create(intake=intake({}), answers={}, title="Probe")
    malformed = replace(
        result.plan,
        systems=(
            GameSystem("a", "a", ("b",)),
            GameSystem("b", "b", ("a", "missing")),
        ),
    )

    assessment = planner.assess(malformed)

    assert not assessment.ok
    assert not assessment.checks["dependencies_resolve"]
    assert not assessment.checks["acyclic_dependencies"]
    assert any("missing" in error for error in assessment.errors)


def test_gameforge_compiles_plan_to_type_safe_acyclic_blueprint() -> None:
    answers = {
        "genre": "shooter",
        "scope": "small",
        "combat": "instantly",
        "era_explicit": "boomer_shooter",
    }
    parsed = intake(answers)
    plan = GameCreationPlanner().create(
        intake=parsed,
        answers=answers,
        title="Signal Run",
    ).plan
    forge = Forge()

    blueprint = GameForge()._build_blueprint(forge, plan)

    assert blueprint.validate() == []
    assert "hero" in blueprint.components
    assert "game_output" in blueprint.components
    assert any(component.kind == "enemy_spawner" for component in blueprint.components.values())
    for wire in blueprint.wires:
        source = blueprint.components[wire.src[0]].port(wire.src[1])
        destination = blueprint.components[wire.dst[0]].port(wire.dst[1])
        assert source.port_type == destination.port_type == "event"


def test_build_plan_preserves_existing_godot_compatibility_flags() -> None:
    answers = {"genre": "shooter", "era_explicit": "extraction_now"}
    result = GameCreationPlanner().create(
        intake=intake(answers),
        answers=answers,
        title="Extraction Probe",
    )

    build_plan = result.plan.to_build_plan()

    assert build_plan["spawn_weapon"] is True
    assert build_plan["extract_late"] is True
    assert build_plan["briefing"]
    assert build_plan["game_creation"]["playtests"]
