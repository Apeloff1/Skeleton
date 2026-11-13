import json

import pytest

from skeleton.qualification.errors import SchemaError
from skeleton.qualification.schema import load_case, load_cases, parse_case

BASE = {"id": "GFM-PERF-09", "gate": "perf", "title": "t", "todo_ref": "P3", "severity": "sev2",
        "params": {"metric": "m", "budgets_ms": {"p95": 10}, "min_samples": 5}}


def mk(**over):
    d = json.loads(json.dumps(BASE))
    d.update(over)
    return d


def test_valid_case_parses():
    c = parse_case(mk())
    assert c.id == "GFM-PERF-09" and c.requires_hardware is False


@pytest.mark.parametrize("cid", ["gfm-perf-01", "GFM-P-01", "GFM-PERF-1", "X-PERF-01"])
def test_bad_ids_rejected(cid):
    with pytest.raises(SchemaError, match="must match"):
        parse_case(mk(id=cid))


def test_unknown_gate_and_field_rejected():
    with pytest.raises(SchemaError, match="gate"):
        parse_case(mk(gate="vibes"))
    with pytest.raises(SchemaError, match="unknown fields"):
        parse_case(mk(owner="x"))


def test_missing_and_mistyped_fields():
    d = mk(); del d["title"]
    with pytest.raises(SchemaError, match="title"):
        parse_case(d)
    with pytest.raises(SchemaError, match="severity"):
        parse_case(mk(severity="sev9"))
    with pytest.raises(SchemaError, match="requires_hardware"):
        parse_case(mk(requires_hardware="yes"))
    with pytest.raises(SchemaError, match="non-empty"):
        parse_case(mk(title="  "))


def test_gate_params_validated():
    with pytest.raises(SchemaError, match="min_samples"):
        parse_case(mk(params={"metric": "m", "budgets_ms": {"p95": 1}}))
    with pytest.raises(SchemaError, match="p50/p95/p99"):
        parse_case(mk(params={"metric": "m", "budgets_ms": {"p90": 1}, "min_samples": 1}))
    with pytest.raises(SchemaError, match="profiles"):
        parse_case(mk(gate="fps", params={"profiles": [45], "sim_hz": 60, "min_ratio": 0.9}))
    with pytest.raises(SchemaError, match="min_ratio"):
        parse_case(mk(gate="fps", params={"profiles": [60], "sim_hz": 60, "min_ratio": 1.5}))
    with pytest.raises(SchemaError, match="must be int"):
        parse_case(mk(params={"metric": "m", "budgets_ms": {"p95": 1}, "min_samples": True}))


def test_load_case_invalid_json(tmp_path):
    p = tmp_path / "x.json"; p.write_text("{nope")
    with pytest.raises(SchemaError, match="invalid JSON"):
        load_case(p)


def test_duplicate_ids_rejected(tmp_path):
    for n in ("a", "b"):
        (tmp_path / f"{n}.json").write_text(json.dumps(mk()))
    with pytest.raises(SchemaError, match="duplicate"):
        load_cases(tmp_path)


def test_shipped_cases_are_valid():
    from skeleton.qualification.__main__ import DEFAULT_CASES
    cases = load_cases(DEFAULT_CASES)
    assert len(cases) >= 9
    assert {c.gate for c in cases} == {"fps", "perf", "soak", "retention", "replay", "promotion"}
    assert all(c.todo_ref.startswith("P3") for c in cases)
