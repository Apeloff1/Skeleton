"""STU-ERAS slice 5: pacing / encounter budgets for eras and campaigns."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from skeleton.simulation.era.scripting import (
    BUDGET_VERSION,
    DEFAULT_BUDGET,
    CampaignBudget,
    EraBudget,
    EraSpec,
    SchemaError,
    check_budget,
    digest,
    evaluate,
    evaluate_campaign,
    measure,
    rest_gaps,
)
from skeleton.simulation.era.scripting.budget import main as budget_main

FIXTURES = Path(__file__).parent / "fixtures" / "stu_eras"


def _raw(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _era(raw: dict) -> EraSpec:
    return EraSpec.from_dict(raw)


def _codes(findings) -> list[str]:
    return [f.code for f in findings]


def _line(n: int, kinds: list[str], *, era_id: str = "line", order: int = 0) -> dict:
    """A linear era r0 -> r1 -> ... with two-way exits and depth == index."""
    rooms = []
    for i in range(n):
        exits = []
        if i + 1 < n:
            exits.append({"direction": "north", "target": f"r{i + 1}"})
        if i > 0:
            exits.append({"direction": "south", "target": f"r{i - 1}"})
        rooms.append(
            {
                "id": f"r{i}",
                "name": f"Room {i}",
                "kind": kinds[i],
                "depth": i,
                "exits": exits,
            }
        )
    return {
        "id": era_id,
        "title": "Line",
        "order": order,
        "start": "r0",
        "citation": "docs/lineage/era.md",
        "rooms": rooms,
    }


def test_fixture_metrics_are_exact():
    m = measure(_era(_raw("bronze")))
    assert m == {
        "rooms": 4,
        "kinds": {"boss": 1, "chamber": 1, "hub": 1, "safe": 1},
        "max_depth": 2,
        "max_hops": 2,
        "bosses": 1,
        "exits": 6,
        "locked_exits": 1,
        "locked_permille": 166,
        "max_rest_gap": 2,
        "stranded": [],
        "max_depth_step": 1,
        "cost": 6,
        "boss_path_cost": {"vault": 6},
    }
    assert measure(_era(_raw("iron")))["cost"] == 4


def test_fixtures_pass_default_budget():
    for name in ("bronze", "iron"):
        report = evaluate(_era(_raw(name)))
        assert report.ok and report.findings == ()
        assert report.digest == digest(_era(_raw(name)))


def test_report_json_is_stable_and_spelling_independent():
    raw = _raw("bronze")
    shuffled = copy.deepcopy(raw)
    shuffled["rooms"] = list(reversed(shuffled["rooms"]))
    for room in shuffled["rooms"]:
        room["exits"] = list(reversed(room.get("exits", [])))
    a, b = evaluate(_era(raw)), evaluate(_era(shuffled))
    assert a.to_json() == b.to_json()
    assert json.loads(a.to_json()) == a.as_dict()
    assert a.to_json() == evaluate(_era(raw)).to_json()


def test_hard_caps_are_errors():
    era = _era(_line(5, ["hub", "arena", "arena", "boss", "boss"]))
    budget = EraBudget(max_rooms=4, max_depth=3, kind_caps=(("arena", 1),), max_cost=10)
    report = evaluate(era, budget)
    assert not report.ok
    assert sorted(_codes(report.errors)) == [
        "budget-bosses",
        "budget-cost",
        "budget-depth",
        "budget-kind",
        "budget-rooms",
    ]
    kind = next(f for f in report.errors if f.code == "budget-kind")
    assert kind.path == "era.line.kinds.arena" and kind.detail == "2 > 1"


def test_min_bosses_error():
    era = _era(_raw("iron"))
    assert _codes(check_budget(era, EraBudget(min_bosses=1))) == ["budget-min-bosses"]


def test_pacing_heuristics_are_warnings():
    kinds = ["hub"] + ["corridor"] * 8 + ["boss"]
    raw = _line(10, kinds)
    raw["rooms"][9]["depth"] = 12  # a 4-level drop across one exit
    raw["rooms"][1]["exits"][0].update(locked=True, key="k")
    report = evaluate(
        _era(raw),
        EraBudget(
            max_hops=5,
            max_rest_gap=4,
            max_path_cost=6,
            max_locked_permille=10,
            max_depth=16,
        ),
    )
    assert report.ok
    assert sorted(_codes(report.warnings)) == [
        "budget-depth-step",
        "budget-hops",
        "budget-locks",
        "budget-path-cost",
        "budget-rest-gap",
    ]
    assert report.metrics["boss_path_cost"] == {"r9": 13}
    assert report.metrics["max_depth_step"] == 4


def test_rest_gaps_and_stranded_rooms():
    raw = _line(4, ["hub", "chamber", "safe", "chamber"])
    assert rest_gaps(_era(raw)) == {"r0": 0, "r1": 1, "r2": 0, "r3": 1}
    # One-way into r3: reachable but can never get back to rest.
    raw["rooms"][3]["exits"] = []
    era = _era(raw)
    assert "r3" not in rest_gaps(era)
    assert measure(era)["stranded"] == ["r3"]
    f = [x for x in check_budget(era) if x.code == "budget-no-rest-path"]
    assert (
        len(f) == 1 and f[0].severity == "warning" and f[0].path == "era.line.rest.r3"
    )


def test_custom_costs_merge_over_defaults():
    budget = EraBudget(costs=(("boss", 50),))
    assert budget.cost_of("boss") == 50 and budget.cost_of("arena") == 3
    assert measure(_era(_raw("bronze")), budget)["cost"] == 51


def test_budget_from_dict_roundtrip_and_validation():
    data = {"max_rooms": 10, "kind_caps": {"boss": 1}, "costs": {"arena": 4}}
    b = EraBudget.from_dict(data)
    assert EraBudget.from_dict(b.to_dict()) == b
    assert b.to_dict()["costs"]["arena"] == 4
    bad = [
        ({"nope": 1}, "unknown-field"),
        ({"max_rooms": 0}, "out-of-range"),
        ({"max_rooms": True}, "bad-int"),
        ({"kind_caps": {"lava": 1}}, "bad-room-kind"),
        ({"costs": []}, "bad-type"),
        ({"min_bosses": 3, "max_bosses": 1}, "bad-budget"),
        ({"max_locked_permille": 1001}, "out-of-range"),
    ]
    for data, code in bad:
        with pytest.raises(SchemaError) as exc:
            EraBudget.from_dict(data)
        assert exc.value.code == code, data


def test_campaign_budget_from_dict():
    cb = CampaignBudget.from_dict(
        {
            "version": BUDGET_VERSION,
            "era": {"max_cost": 9},
            "campaign": {"rising_cost": False},
        }
    )
    assert cb.era.max_cost == 9 and cb.rising_cost is False
    assert CampaignBudget.from_dict(cb.to_dict()) == cb
    for data, code in [
        ({"version": "x"}, "bad-schema"),
        ({"campaign": {"rising_cost": 1}}, "bad-bool"),
        ({"campaign": {"max_total_rooms": 0}}, "out-of-range"),
        ({"extra": {}}, "unknown-field"),
    ]:
        with pytest.raises(SchemaError) as exc:
            CampaignBudget.from_dict(data)
        assert exc.value.code == code


def test_campaign_rollup_orders_and_flags_regression():
    eras = [_era(_raw("iron")), _era(_raw("bronze"))]
    rep = evaluate_campaign(eras)
    assert [r.era for r in rep.eras] == ["bronze", "iron"]
    assert rep.totals == {
        "eras": 2,
        "rooms": 7,
        "cost": 10,
        "bosses": 1,
        "cost_curve": [["bronze", 6], ["iron", 4]],
        "errors": 0,
        "warnings": 1,
    }
    assert _codes(rep.findings) == ["difficulty-regression"] and rep.ok
    quiet = evaluate_campaign(eras, CampaignBudget(rising_cost=False))
    assert quiet.findings == ()
    tight = evaluate_campaign(eras, CampaignBudget(max_total_rooms=6, max_total_cost=9))
    assert not tight.ok
    assert sorted(_codes(tight.findings))[:2] == [
        "budget-total-cost",
        "budget-total-rooms",
    ]
    assert rep.to_json() == evaluate_campaign(list(reversed(eras))).to_json()


def test_campaign_rejects_bad_input():
    with pytest.raises(SchemaError) as exc:
        evaluate_campaign([_raw("bronze")])
    assert exc.value.code == "bad-type"
    e = _era(_raw("bronze"))
    with pytest.raises(SchemaError) as exc:
        evaluate_campaign([e, e])
    assert exc.value.code == "duplicate-era"
    with pytest.raises(SchemaError):
        evaluate(_raw("bronze"))
    with pytest.raises(SchemaError):
        check_budget(e, {"max_rooms": 1})


def test_budget_does_not_mutate_inputs():
    raw = _raw("bronze")
    snap = copy.deepcopy(raw)
    era = _era(raw)
    before = era.to_dict()
    evaluate(era)
    evaluate_campaign([era])
    assert raw == snap and era.to_dict() == before
    assert DEFAULT_BUDGET == EraBudget()


def test_cli_reports_and_exit_codes(tmp_path, capsys):
    files = [str(FIXTURES / "bronze.json"), str(FIXTURES / "iron.json")]
    assert budget_main(files + ["--campaign"]) == 0
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert [x.get("era") for x in lines[:2]] == ["bronze", "iron"]
    assert lines[2]["campaign"] is True and lines[2]["totals"]["cost"] == 10

    tight = tmp_path / "b.json"
    tight.write_text(json.dumps({"era": {"max_rooms": 3}}))
    assert budget_main(files + ["--budget", str(tight)]) == 1
    out = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert out[0]["ok"] is False and out[1]["ok"] is True

    bad = tmp_path / "bad.json"
    bad.write_text("{nope")
    assert budget_main(files + ["--budget", str(bad)]) == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "bad-json"

    assert budget_main([str(tmp_path / "missing.json")]) == 1
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "missing-file"


def test_mirror_package_matches():
    root = Path(__file__).resolve().parents[1]
    a = root / "skeleton" / "simulation" / "era" / "scripting"
    b = root / "skeleton" / "ai" / "simulation" / "era" / "scripting"
    for name in ("budget.py", "__init__.py"):
        assert (a / name).read_bytes() == (b / name).read_bytes()
