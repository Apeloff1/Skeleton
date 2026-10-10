"""STU-ERAS slice 2: composition/inheritance and validation CLI."""

from __future__ import annotations

import copy
import json

import pytest

from skeleton.simulation.era.scripting import (
    SCHEMA_VERSION,
    SchemaError,
    compose_era,
    load_composed,
    merge_room,
    resolve_room,
)
from skeleton.simulation.era.scripting.cli import main


def _base():
    return {
        "schema": SCHEMA_VERSION,
        "id": "bronze",
        "title": "Bronze Age",
        "order": 1,
        "start": "gate",
        "citation": "docs/lineage/era.md",
        "tags": ["ancient"],
        "rooms": [
            {"id": "gate", "name": "Gate", "kind": "hub", "tags": ["lit"],
             "exits": [{"direction": "north", "target": "hall"}]},
            {"id": "hall", "name": "Hall", "exits": [{"direction": "south", "target": "gate"}]},
        ],
    }


def test_merge_room_child_wins_and_unions_tags():
    out = merge_room(
        {"id": "a", "name": "A", "tags": ["x", "y"], "exits": [{"direction": "north", "target": "b"}]},
        {"name": "A2", "tags": ["y", "z"], "exits": [{"direction": "north", "target": "c"},
                                                      {"direction": "east", "target": "d"}]},
    )
    assert out["name"] == "A2"
    assert out["tags"] == ["x", "y", "z"]
    assert out["exits"] == [{"direction": "north", "target": "c"}, {"direction": "east", "target": "d"}]


def test_resolve_room_template_chain():
    templates = {
        "lit_room": {"tags": ["lit"], "kind": "chamber"},
        "vault": {"extends": "lit_room", "kind": "secret", "depth": 3},
    }
    out = resolve_room({"extends": "vault", "id": "v", "name": "Vault"}, templates)
    assert out == {"tags": ["lit"], "kind": "secret", "depth": 3, "id": "v", "name": "Vault"}


def test_room_template_cycle_and_unknown():
    with pytest.raises(SchemaError) as e:
        resolve_room({"extends": "a"}, {"a": {"extends": "b"}, "b": {"extends": "a"}})
    assert e.value.code == "extends-cycle"
    with pytest.raises(SchemaError) as e:
        resolve_room({"extends": "nope"}, {})
    assert e.value.code == "unknown-template"


def test_era_inheritance_merges_rooms_by_id():
    child = {
        "extends": "bronze",
        "id": "late_bronze",
        "title": "Late Bronze Age",
        "order": 2,
        "tags": ["collapse"],
        "rooms": [
            {"id": "hall", "name": "Ruined Hall", "exits": [{"direction": "east", "target": "pit"}]},
            {"id": "pit", "name": "Pit", "kind": "boss", "exits": [{"direction": "west", "target": "hall"}]},
        ],
    }
    era = load_composed(child, {"bronze": _base()})
    assert era.id == "late_bronze" and era.order == 2
    assert era.tags == ("ancient", "collapse")
    assert era.room_ids == ("gate", "hall", "pit")
    assert era.room("hall").name == "Ruined Hall"
    assert [e.direction for e in era.room("hall").exits] == ["south", "east"]


def test_compose_does_not_mutate_inputs():
    base = _base()
    snapshot = copy.deepcopy(base)
    child = {"extends": "bronze", "id": "x", "rooms": [{"id": "gate", "tags": ["new"]}]}
    child_snap = copy.deepcopy(child)
    compose_era(child, {"bronze": base})
    assert base == snapshot and child == child_snap


def test_era_extends_errors():
    with pytest.raises(SchemaError) as e:
        compose_era({"extends": "missing"}, {})
    assert e.value.code == "unknown-base"
    with pytest.raises(SchemaError) as e:
        compose_era({"extends": "a"}, {"a": {"extends": "b"}, "b": {"extends": "a"}})
    assert e.value.code == "extends-cycle"
    with pytest.raises(SchemaError) as e:
        compose_era({"extends": 5}, {})
    assert e.value.code == "bad-extends"


def test_extends_depth_limit():
    bases = {f"e{i}": {"extends": f"e{i + 1}"} for i in range(12)}
    bases["e12"] = {}
    with pytest.raises(SchemaError) as e:
        compose_era({"extends": "e0"}, bases)
    assert e.value.code == "extends-too-deep"


def test_composed_result_is_still_schema_gated():
    child = {"extends": "bronze", "id": "bad", "rooms": [{"id": "gate", "exits": [
        {"direction": "up", "target": "nowhere"}]}]}
    with pytest.raises(SchemaError) as e:
        load_composed(child, {"bronze": _base()})
    assert e.value.code == "dangling-exit"


def test_era_rooms_resolve_templates():
    base = _base()
    base["rooms"][1]["extends"] = "boss_room"
    era = load_composed(base, templates={"boss_room": {"kind": "boss", "tags": ["danger"]}})
    assert era.room("hall").kind == "boss"
    assert era.room("hall").tags == ("danger",)


def test_cli_valid_and_invalid(tmp_path, capsys):
    base = tmp_path / "bronze.json"
    base.write_text(json.dumps(_base()))
    child = tmp_path / "late.json"
    child.write_text(json.dumps({"extends": "bronze", "id": "late", "title": "Late"}))
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert main([str(base)]) == 0
    assert main([str(child), "--base", str(base)]) == 0
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert lines[0]["ok"] and lines[0]["rooms"] == 2
    assert lines[1] == {"file": str(child), "ok": True, "era": "late", "rooms": 2}
    assert main([str(bad), str(base)]) == 1
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert lines[0]["error"]["code"] == "bad-json" and lines[1]["ok"]


def test_cli_bad_templates_and_missing(tmp_path, capsys):
    tpl = tmp_path / "t.json"
    tpl.write_text("[]")
    assert main([str(tmp_path / "x.json"), "--templates", str(tpl)]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "bad-templates"
    assert main([str(tmp_path / "missing.json")]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "missing-file"


def test_ai_mirror_exports_match():
    import skeleton.ai.simulation.era.scripting as ai
    import skeleton.simulation.era.scripting as main_pkg

    assert ai.__all__ == main_pkg.__all__
