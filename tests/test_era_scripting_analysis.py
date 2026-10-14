"""STU-ERAS slice 3: room-graph analysis, campaign checks, example fixtures."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from skeleton.simulation.era.scripting import (
    EraSpec,
    Finding,
    SchemaError,
    assert_clean,
    check_campaign,
    check_era,
    distances,
    load_era_json,
    load_eras,
    reachable,
    shortest_path,
    summarize,
)
from skeleton.simulation.era.scripting.cli import main as cli_main

FIXTURES = Path(__file__).parent / "fixtures" / "stu_eras"


def _raw(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _era(raw: dict) -> EraSpec:
    return EraSpec.from_dict(raw)


def _codes(findings) -> list[str]:
    return [f.code for f in findings]


def test_fixtures_load_and_validate_via_cli(capsys):
    files = sorted(FIXTURES.glob("*.json"))
    assert [p.stem for p in files] == ["bronze", "iron"]
    assert cli_main([str(p) for p in files]) == 0
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert all(line["ok"] for line in lines)


def test_fixture_campaign_has_no_errors():
    eras = load_eras([_raw("iron"), _raw("bronze")])
    assert [e.id for e in eras] == ["bronze", "iron"]
    findings = check_campaign(eras)
    assert_clean(findings)
    assert _codes(findings) == ["behind-lock"]  # bronze vault sits behind a key


def test_reachable_is_deterministic_bfs_in_direction_order():
    era = load_era_json(FIXTURES / "bronze.json")
    assert reachable(era) == ("gate", "forum", "smithy", "vault")
    assert reachable(era, allow_locked=False) == ("gate", "forum", "smithy")
    assert distances(era) == {"gate": 0, "forum": 1, "smithy": 1, "vault": 2}


def test_shortest_path():
    era = load_era_json(FIXTURES / "bronze.json")
    assert shortest_path(era, "gate", "vault") == ("gate", "forum", "vault")
    assert shortest_path(era, "gate", "vault", allow_locked=False) == ()
    assert shortest_path(era, "smithy", "smithy") == ("smithy",)
    with pytest.raises(SchemaError) as exc:
        shortest_path(era, "gate", "nowhere")
    assert exc.value.code == "unknown-room"


def test_unreachable_room_is_error_and_assert_clean_raises():
    raw = _raw("iron")
    raw["rooms"].append({"id": "island", "name": "Island", "exits": [{"direction": "east", "target": "camp"}]})
    findings = check_era(_era(raw))
    assert "unreachable-room" in _codes(findings)
    with pytest.raises(SchemaError) as exc:
        assert_clean(findings)
    assert exc.value.code == "unreachable-room"
    assert exc.value.path == "era.iron.rooms[3]"


def test_one_way_and_dead_end_are_warnings():
    raw = _raw("iron")
    raw["rooms"][2]["exits"] = []  # keep: no way back, no exits
    findings = check_era(_era(raw))
    by_code = {f.code: f for f in findings}
    assert by_code["dead-end"].severity == "warning"
    assert by_code["one-way-exit"].severity == "warning"
    assert by_code["one-way-exit"].path == "era.iron.rooms[1].exits[1]"
    assert_clean(findings)  # warnings alone never raise


def test_terminal_rooms_are_not_dead_ends_but_cannot_start():
    raw = _raw("iron")
    raw["rooms"][2]["kind"] = "boss"
    raw["rooms"][2]["exits"] = []
    assert "dead-end" not in _codes(check_era(_era(raw)))
    raw2 = _raw("iron")
    raw2["rooms"][0]["kind"] = "boss"
    assert "bad-start-kind" in _codes(check_era(_era(raw2)))


def test_multiple_bosses_warn():
    raw = _raw("iron")
    raw["rooms"][1]["kind"] = "boss"
    raw["rooms"][2]["kind"] = "boss"
    f = [x for x in check_era(_era(raw)) if x.code == "multiple-bosses"]
    assert f and f[0].detail == "pass,keep" and f[0].severity == "warning"


def test_campaign_duplicate_order_and_id():
    bronze = _era(_raw("bronze"))
    iron_raw = _raw("iron")
    iron_raw["order"] = 1
    findings = check_campaign([bronze, _era(iron_raw), bronze])
    codes = _codes(errors := [f for f in findings if f.severity == "error"])
    assert codes.count("duplicate-order") == 1
    assert codes.count("duplicate-era") == 1
    assert errors[0].path == "eras[1].order"


def test_campaign_rejects_raw_dicts():
    with pytest.raises(SchemaError) as exc:
        check_campaign([_raw("iron")])
    assert exc.value.code == "bad-type"


def test_summary_is_stable_and_json_ready():
    era = load_era_json(FIXTURES / "bronze.json")
    s = summarize(era)
    assert s == {
        "era": "bronze",
        "order": 1,
        "rooms": 4,
        "reachable": 4,
        "max_hops": 2,
        "kinds": {"boss": 1, "chamber": 1, "hub": 1, "safe": 1},
        "errors": 0,
        "warnings": 1,
    }
    assert json.loads(json.dumps(s)) == s
    assert summarize(era) == s


def test_analysis_does_not_mutate_and_finding_dict():
    raw = _raw("bronze")
    snap = copy.deepcopy(raw)
    era = _era(raw)
    check_era(era)
    summarize(era)
    assert raw == snap
    f = Finding("x", "p", "d")
    assert f.as_dict() == {"code": "x", "path": "p", "detail": "d", "severity": "error"}


def test_mirror_package_matches():
    root = Path(__file__).resolve().parents[1]
    a = root / "skeleton" / "simulation" / "era" / "scripting"
    b = root / "skeleton" / "ai" / "simulation" / "era" / "scripting"
    for name in ("analysis.py", "__init__.py"):
        assert (a / name).read_bytes() == (b / name).read_bytes()
