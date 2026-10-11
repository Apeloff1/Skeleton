"""Cognitive NPC world integration: paid cooperative cities, memory and ties."""
from __future__ import annotations

from dataclasses import asdict, replace
import json

import pytest

from skeleton.game.generation.original_foundation_compiler import FoundationError
from skeleton.game.generation.original_world_living_10x_compiler import living_for
from skeleton.game.generation.original_world_product_terrain import cell_at
from skeleton.game.generation.original_world_product_session import (
    ProductAction, create_product, step_product, product_save, product_restore,
    validate_product,
)
from skeleton.game.generation.original_world_product_cli import parse_command, main
from skeleton.game.generation.original_world_npc_cognition_v2 import (
    CivicProject, PROJECT_COSTS, _bond_change, cognition_report,
)


def game(n=2):
    law = living_for(0, "puzzle", "lattice", "trophic", "sandbox")
    return create_product(law.index, inhabitants=n)


def act(s, verb, layer="npc", amount=1, x=0, y=0, target=-1, option=""):
    return step_product(s, ProductAction(
        layer, verb, amount=amount, x=x, y=y,
        target=target, option=option,
    ))[0]


def skilled(s):
    """Two genuine bodies independently work at same accessible depot site."""
    a, b, *others = s.society.inhabitants
    a = replace(a, x=0, y=0, profession="builder")
    b = replace(b, x=0, y=0, profession="engineer")
    return replace(s, society=replace(s.society, inhabitants=(a,b,*others)))


def test_two_distinct_skilled_npcs_complete_real_material_backed_hearth():
    s = skilled(game())
    initial = (s.terrain.lumber, s.terrain.masonry, s.terrain.shelter)
    s = act(s, "project", option="hearth")
    project = s.cognition.projects[0]
    assert project.status == "open"
    assert project.contributors == ()
    assert s.terrain.lumber == initial[0] - 2
    assert s.terrain.masonry == initial[1] - 1
    assert cell_at(s.terrain, 0, 0).building == ""
    s, proof = step_product(s, ProductAction("causal", "end_turn"))
    assert s.cognition.projects[0].status == "completed"
    assert s.cognition.projects[0].contributors == (0, 1)
    assert s.terrain.shelter == initial[2] + 1
    assert cell_at(s.terrain, 0, 0).building == "hearth"
    assert s.terrain.lumber == initial[0] - 2
    assert s.terrain.masonry == initial[1] - 1
    assert s.cognition.day == 1
    assert product_restore(product_save(s)) == s
    assert "citizens" in " ".join(proof.changes)


def test_one_worker_cannot_fake_two_different_labor_signatures():
    s = game(1)
    worker = replace(s.society.inhabitants[0], profession="builder")
    s = replace(s, society=replace(s.society, inhabitants=(worker,)))
    s = act(s, "project", option="hearth")
    s = act(s, "end_turn", layer="causal")
    assert s.cognition.projects[0].contributors == (0,)
    assert s.cognition.projects[0].status == "open"
    assert cell_at(s.terrain, 0, 0).building == ""
    s = act(s, "end_turn", layer="causal")
    assert s.cognition.projects[0].contributors == (0,)
    assert s.cognition.projects[0].status == "open"
    assert s.terrain.shelter == 0


def test_cancellation_refunds_exact_escrow_but_never_creates_structures():
    s = game()
    start = (s.terrain.lumber, s.terrain.masonry)
    s = act(s, "project", option="hearth")
    assert s.terrain.lumber == start[0] - 2
    assert s.terrain.masonry == start[1] - 1
    s = act(s, "cancel_project", target=0)
    assert s.cognition.projects[0].status == "cancelled"
    assert (s.terrain.lumber, s.terrain.masonry) == start
    assert cell_at(s.terrain, 0, 0).building == ""
    with pytest.raises(FoundationError):
        act(s, "cancel_project", target=0)


def test_invalid_terrain_and_double_build_are_rejected_fail_closed():
    s = game()
    original = product_save(s)
    with pytest.raises(FoundationError):
        act(s, "project", option="fictional-tower")
    with pytest.raises(FoundationError):
        act(s, "project", option="beacon", x=2**22)
    assert original == product_save(s)
    s = act(s, "project", option="hearth")
    with pytest.raises(FoundationError):
        act(s, "project", option="hearth")
    assert len(s.cognition.projects) == 1


def test_financially_escrowed_civic_mill_requires_distinct_three_people():
    s = game(3)
    people = list(s.society.inhabitants)
    for i in range(3):
        people[i] = replace(people[i], x=0, y=0,
                            profession="builder" if i != 1 else "engineer")
    s = replace(s, society=replace(s.society, inhabitants=tuple(people)))
    assert PROJECT_COSTS["mill"] == (1, 3, 3)
    s = act(s, "project", option="mill")
    assert s.terrain.masonry == 0
    s = act(s, "end_turn", layer="causal")
    p = s.cognition.projects[0]
    assert p.status == "completed"
    assert p.contributors == (0, 1, 2)
    assert cell_at(s.terrain, 0, 0).building == "mill"
    assert s.terrain.masonry == 0


def test_loneliness_causes_realtime_socializing_and_real_remembered_friendship():
    s = skilled(game())
    minds = tuple(replace(m, loneliness=20, stress=0)
                  for m in s.cognition.minds)
    s = replace(s, cognition=replace(s.cognition, minds=minds))
    s = act(s, "end_turn", layer="causal")
    assert len(s.cognition.bonds) == 1
    bond = s.cognition.bonds[0]
    assert (bond.left, bond.right) == (0, 1)
    assert bond.trust > 0 and bond.affinity > 0
    assert s.cognition.minds[0].loneliness < 20
    assert s.cognition.minds[1].loneliness < 20
    assert any(event.subject == "friend" for event in s.cognition.minds[0].memories)
    assert any(event.witness == 0 for event in s.cognition.minds[1].memories)


def test_individual_thought_history_conserves_people_and_stocks_for_many_ticks():
    s = game(6)
    for _ in range(18):
        s = act(s, "end_turn", layer="causal")
        validate_product(s)
        assert len(s.society.inhabitants) == len(s.cognition.minds) == 6
        assert all(len(m.memories) <= 16 for m in s.cognition.minds)
        assert all(0 <= x.hunger <= 20 for x in s.society.inhabitants)
        assert all(0 <= x.health <= 20 for x in s.society.inhabitants)
    restored = product_restore(product_save(s))
    assert restored == s


def test_project_and_social_parser_expose_genuine_user_level_commands(capsys):
    assert parse_command("npc project hearth 0 0", (0, 0)) == ProductAction(
        "npc", "project", option="hearth", x=0, y=0,
    )
    assert parse_command("npc cancel_project 2", (0, 0)).target == 2
    assert main([
        "--base", "0", "--form", "puzzle", "--architecture", "lattice",
        "--system", "trophic", "--arc", "sandbox",
        "--actions-json", '[{"layer":"npc","verb":"project","option":"hearth"}]',
        "--npc-report",
    ]) == 0
    packet = json.loads(capsys.readouterr().out)
    data = packet["product"]["npc_cognition"]
    assert data["civic_projects"][0]["escrow_wood"] == 2
    assert data["civic_projects"][0]["status"] == "open"


def test_cognition_report_distinguishes_real_people_from_synthetic_generated_world_count():
    s = game(12)
    report = cognition_report(s.cognition, s.society, s.terrain)
    assert report["citizens"] == 12
    assert report["verified_world_observations"] == 0
    assert report["report_not_an_llm"] is True
    assert report["completed_constructed_projects"] == 0
