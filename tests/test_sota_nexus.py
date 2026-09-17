from __future__ import annotations

import json

import pytest

from skeleton.game.catalog_data import pack as catalog_pack
from skeleton.game.emit_tree import build, public_card
from skeleton.game.nexus_sim import NexusSimError, simulate
from skeleton.game.zip_bundle import bundles


def test_nexus_sim_extracts_deterministically() -> None:
    left = simulate(seed=8847291, ticks=32)
    right = simulate(seed=8847291, ticks=32)
    assert left["digest"] == right["digest"]
    assert left["passed"] is True
    assert left["extracted"] >= 1
    assert left["every_frame"] is False
    assert left["sota_ready"] is False
    assert left["stored_prose"] == 0
    other = simulate(seed=8847292, ticks=32)
    assert other["digest"] != left["digest"]
    with pytest.raises(NexusSimError):
        simulate(ticks=2)


def test_catalog_and_emit_tree_have_required_files() -> None:
    catalogs = catalog_pack(8847291)
    assert catalogs["n"] >= 20
    assert catalogs["items"]["n"] == 8
    assert catalogs["quests"]["n"] == 6
    tree = build(seed=8847291)
    names = set(tree["files"])
    for required in (
        "project.godot",
        "world.json",
        "world.gd",
        "world.tscn",
        "player.gd",
        "jeeves/",
        "heat/",
        "forge/",
        "extract/",
        "reports/build_report.md",
        "data/spec.json",
    ):
        assert required in names
    assert "godot.exe" not in names
    assert tree["godot_binary"] == 0
    assert tree["valid"] == 1
    assert tree["contents"]["project.godot"].startswith("; Engine")
    assert "autoload" in tree["contents"]["project.godot"]
    card = public_card(tree)
    assert "contents" not in card
    assert card["digest"] == tree["digest"]
    assert build(seed=8847291)["digest"] == tree["digest"]


def test_three_bundles_share_spec() -> None:
    pack = bundles(seed=8847291)
    assert pack["n"] == 3
    assert pack["spec"] == "data/spec.json"
    assert {row["name"] for row in pack["bundles"]} == {"godot_project", "web_stub", "data_only"}
    assert all(row["godot_binary"] == 0 for row in pack["bundles"])
    assert bundles(seed=8847291)["bundles"][0]["digest"] == pack["bundles"][0]["digest"]


def test_cli_nexus_and_packtree(capsys: pytest.CaptureFixture[str]) -> None:
    from skeleton.__main__ import main

    assert main(["nexus", "--seed", "8847291"]) == 0
    sim = json.loads(capsys.readouterr().out)
    assert sim["ok"] is True
    assert sim["passed"] is True
    assert sim["sota_ready"] is False
    assert main(["packtree", "--seed", "8847291"]) == 0
    tree = json.loads(capsys.readouterr().out)
    assert tree["valid"] == 1
    assert tree["godot_binary"] == 0
    assert main(["bundles", "--seed", "8847291"]) == 0
    pack = json.loads(capsys.readouterr().out)
    assert pack["n"] == 3
