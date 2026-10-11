"""No fake missions: 16 authored disciplines × 10 overlays × state evidence."""
from __future__ import annotations
from dataclasses import asdict
import json

from skeleton.game.generation.original_foundation_compiler import ROOTS, REGIMES, REGIME_COUNT
from skeleton.game.generation.original_world_living_10x_compiler import living_for
from skeleton.game.generation.original_world_product_session import (
    ProductAction, create_product, step_product,
)
from skeleton.game.generation.original_world_product_missions import (
    DOMAIN_EVIDENCE, REGIME_EVIDENCE, mission_report,
)
from skeleton.game.generation.original_world_product_cli import main


def game(index: int):
    return create_product(living_for(
        index, "puzzle", "lattice", "trophic", "sandbox",
    ).index, inhabitants=1)


def action(game_state, layer: str, verb: str, amount=1, x=0, y=0, target=-1):
    return step_product(
        game_state, ProductAction(layer, verb, amount, x, y, target)
    )[0]


def test_all_160_domain_regime_intersections_are_physical_missions() -> None:
    assert len(DOMAIN_EVIDENCE) == 16
    assert len(REGIME_EVIDENCE) == 10
    for domain_i in range(16):
        for regime_i in range(10):
            world = game(domain_i * 8 * REGIME_COUNT + regime_i * 8)
            report = mission_report(world)
            assert report["domain"] == ROOTS[domain_i * 8].domain
            assert report["regime_id"] == REGIMES[regime_i * 8].regime_id
            assert report["authored_premise"] == ROOTS[domain_i * 8].invariant
            assert report["authored_lever"] == ROOTS[domain_i * 8].lever
            assert len(report["missions"]) == 3
            assert all(p["witness"] for p in report["missions"])
            assert report["global_victory_certified"] is False
            assert report["bespoke_world_mechanic_fully_implemented"] is False


def test_materials_root_uses_real_mined_and_collected_stone_evidence() -> None:
    index = next(n * REGIME_COUNT for n, r in enumerate(ROOTS)
                 if r.domain == "materials")
    s = game(index)
    previous = mission_report(s)
    assert not previous["missions"][0]["verified"]
    s = action(s, "terrain", "mine")
    after = mission_report(s)
    assert after["missions"][0]["verified"]
    assert after["verified_local_milestones"] >= 1


def test_social_world_requires_material_aid_to_real_named_resident() -> None:
    index = next(n * REGIME_COUNT for n, r in enumerate(ROOTS)
                 if r.domain == "affection")
    s = game(index)
    prior = mission_report(s)
    assert not prior["missions"][0]["verified"]
    s = action(s, "studio", "gift", target=0)
    after = mission_report(s)
    assert after["missions"][0]["verified"]
    assert s.terrain.provisions == 4


def test_original_governance_is_not_completed_by_reading_blueprint() -> None:
    index = next(n * REGIME_COUNT for n, r in enumerate(ROOTS)
                 if r.domain == "governance")
    s = game(index)
    first = mission_report(s)
    assert first["missions"][0]["current"] == 0
    assert first["verified_local_milestones"] == 0
    s = action(s, "causal", "intervene")
    second = mission_report(s)
    assert second["missions"][0]["verified"]
    assert second["missions"][2]["verified"] is False
    s = action(s, "causal", "end_turn")
    third = mission_report(s)
    assert third["missions"][2]["verified"]


def test_quest_director_publishes_full_root_provenance_in_cli(capsys) -> None:
    assert main([
        "--base", "0", "--form", "puzzle", "--architecture", "lattice",
        "--system", "trophic", "--arc", "sandbox",
        "--actions-json", '[{"layer":"causal","verb":"intervene"},'
                          '{"layer":"causal","verb":"end_turn"}]',
        "--missions",
    ]) == 0
    packet = json.loads(capsys.readouterr().out)
    missions = packet["product"]["missions"]
    assert missions["authored_root_id"].startswith("root-")
    assert len(missions["missions"]) == 3
    assert not missions["global_victory_certified"]
    assert missions["authorial_ending_policy"]


def test_readonly_missions_never_change_resources_or_event_chains() -> None:
    s = game(0)
    before = asdict(s)
    for _ in range(3):
        mission_report(s)
    assert before == asdict(s)
