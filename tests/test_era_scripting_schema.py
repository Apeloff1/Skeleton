"""STU-ERAS slice 1: era/room schema and loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.simulation.era.scripting import (
    SCHEMA_VERSION,
    EraSpec,
    SchemaError,
    load_era,
    load_era_json,
    load_eras,
)

ROOT = Path(__file__).resolve().parents[1]


def _era(**over):
    data = {
        "schema": SCHEMA_VERSION,
        "id": "bronze",
        "title": "Bronze Age",
        "order": 1,
        "start": "gate",
        "citation": "docs/lineage/era.md",
        "tags": ["ancient"],
        "rooms": [
            {
                "id": "gate",
                "name": "Gate",
                "kind": "hub",
                "exits": [{"direction": "north", "target": "hall"}],
            },
            {
                "id": "hall",
                "name": "Hall",
                "depth": 1,
                "exits": [
                    {"direction": "south", "target": "gate"},
                    {"direction": "up", "target": "vault", "locked": True, "key": "bronze_key"},
                ],
            },
            {"id": "vault", "name": "Vault", "kind": "secret", "depth": 2},
        ],
    }
    data.update(over)
    return data


def _code(data) -> str:
    with pytest.raises(SchemaError) as info:
        load_era(data)
    return info.value.code


def test_valid_era_loads_and_indexes_rooms() -> None:
    era = load_era(_era())
    assert isinstance(era, EraSpec)
    assert era.room_ids == ("gate", "hall", "vault")
    assert era.room("hall").exit("up").key == "bronze_key"
    assert era.room("vault").kind == "secret"
    assert era.room("gate").exit("east") is None


def test_round_trip_is_stable() -> None:
    era = load_era(_era())
    again = load_era(era.to_dict())
    assert again == era
    assert again.to_dict() == era.to_dict()


@pytest.mark.parametrize(
    ("over", "code"),
    [
        ({"schema": "stu-eras/0"}, "bad-schema"),
        ({"id": "Bad Id"}, "bad-ident"),
        ({"title": ""}, "bad-text"),
        ({"citation": "has spaces"}, "bad-citation"),
        ({"start": "nowhere"}, "dangling-start"),
        ({"rooms": []}, "no-rooms"),
        ({"order": -1}, "out-of-range"),
        ({"order": True}, "bad-int"),
        ({"tags": ["a", "a"]}, "duplicate-tag"),
        ({"surprise": 1}, "unknown-field"),
    ],
)
def test_era_level_failures_are_fail_closed(over, code) -> None:
    assert _code(_era(**over)) == code


def test_room_and_exit_failures() -> None:
    data = _era()
    data["rooms"].append({"id": "gate", "name": "Dup"})
    assert _code(data) == "duplicate-room"

    data = _era()
    data["rooms"][0]["exits"].append({"direction": "north", "target": "vault"})
    assert _code(data) == "duplicate-exit"

    data = _era()
    data["rooms"][0]["exits"][0]["target"] = "missing"
    assert _code(data) == "dangling-exit"

    data = _era()
    data["rooms"][0]["exits"][0]["direction"] = "sideways"
    assert _code(data) == "bad-direction"

    data = _era()
    data["rooms"][1]["exits"][1].pop("key")
    assert _code(data) == "locked-without-key"

    data = _era()
    data["rooms"][2]["kind"] = "lobby"
    assert _code(data) == "bad-room-kind"


def test_error_carries_path_and_dict() -> None:
    data = _era()
    data["rooms"][1]["exits"][0]["target"] = "missing"
    with pytest.raises(SchemaError) as info:
        load_era(data)
    assert info.value.as_dict() == {
        "code": "dangling-exit",
        "path": "era.rooms[1].exits[0].target",
        "detail": "no room 'missing'",
    }


def test_json_loader_text_bytes_and_path(tmp_path) -> None:
    text = json.dumps(_era())
    assert load_era_json(text).id == "bronze"
    assert load_era_json(text.encode()).id == "bronze"
    path = tmp_path / "bronze.json"
    path.write_text(text, encoding="utf-8")
    assert load_era_json(path).id == "bronze"
    with pytest.raises(SchemaError) as info:
        load_era_json("{not json")
    assert info.value.code == "bad-json"
    with pytest.raises(SchemaError) as info:
        load_era_json(tmp_path / "absent.json")
    assert info.value.code == "missing-file"


def test_load_eras_sorts_and_rejects_duplicates() -> None:
    eras = load_eras([_era(id="iron", order=2), _era(), _era(id="atomic", order=2)])
    assert [e.id for e in eras] == ["bronze", "atomic", "iron"]
    with pytest.raises(SchemaError) as info:
        load_eras([_era(), _era()])
    assert info.value.code == "duplicate-era"


def test_ai_mirror_is_exact() -> None:
    src = ROOT / "skeleton/simulation/era/scripting"
    dst = ROOT / "skeleton/ai/simulation/era/scripting"
    names = sorted(p.name for p in src.glob("*.py"))
    assert names == sorted(p.name for p in dst.glob("*.py"))
    for name in names:
        assert (src / name).read_bytes() == (dst / name).read_bytes(), name
