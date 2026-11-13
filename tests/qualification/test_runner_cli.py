import json

from skeleton.qualification import aggregate, parse_case, run_cases
from skeleton.qualification.__main__ import DEFAULT_CASES, main
from skeleton.qualification.evidence import load_evidence
from skeleton.qualification.report import to_json, to_markdown
from skeleton.qualification.verdict import CaseResult, Verdict

from .conftest import HEAD, OTHER

PERF = parse_case({"id": "GFM-PERF-77", "gate": "perf", "title": "t", "todo_ref": "P3", "severity": "sev2",
                   "params": {"metric": "m", "budgets_ms": {"p95": 10}, "min_samples": 3}})
HW = parse_case({"id": "GFM-FPS-77", "gate": "fps", "title": "t", "todo_ref": "P3", "severity": "sev2",
                 "requires_hardware": True, "params": {"profiles": [60], "sim_hz": 60, "min_ratio": 0.9}})


def test_aggregate_worst_wins_and_empty_is_blocked():
    mk = lambda v: CaseResult("c", "g", v)
    assert aggregate([]) is Verdict.BLOCKED
    assert aggregate([mk(Verdict.PASS)]) is Verdict.PASS
    assert aggregate([mk(Verdict.PASS), mk(Verdict.BLOCKED)]) is Verdict.BLOCKED
    assert aggregate([mk(Verdict.BLOCKED), mk(Verdict.FAIL), mk(Verdict.PASS)]) is Verdict.FAIL


def test_no_evidence_is_blocked_not_pass(head):
    [r] = run_cases([PERF], {}, head)
    assert r.verdict is Verdict.BLOCKED and r.reasons == ("no evidence recorded",)


def test_stale_head_is_blocked(write_evidence):
    ev = load_evidence(write_evidence("GFM-PERF-77", {"samples_ms": [1, 2, 3]}, sha=OTHER))
    [r] = run_cases([PERF], ev, HEAD)
    assert r.verdict is Verdict.BLOCKED and "not head" in r.reasons[0]


def test_pass_and_fail(write_evidence):
    ev = load_evidence(write_evidence("GFM-PERF-77", {"samples_ms": [1, 2, 3]}))
    assert run_cases([PERF], ev, HEAD)[0].verdict is Verdict.PASS
    ev = load_evidence(write_evidence("GFM-PERF-77", {"samples_ms": [1, 2, 30]}))
    assert run_cases([PERF], ev, HEAD)[0].verdict is Verdict.FAIL


def test_hardware_case_rejects_ci_evidence(write_evidence):
    data = {"runs": {"60": {"frame_ms": [16.0], "sim_hz": 60, "sim_state_hash": "x"}}}
    ev = load_evidence(write_evidence("GFM-FPS-77", data, source="ci"))
    [r] = run_cases([HW], ev, HEAD)
    assert r.verdict is Verdict.BLOCKED and "CI-sourced" in r.reasons[0]
    ev = load_evidence(write_evidence("GFM-FPS-77", data, source="device"))
    assert run_cases([HW], ev, HEAD)[0].verdict is Verdict.BLOCKED
    assert run_cases([HW], ev, HEAD, device_verifier=lambda e: True)[0].verdict is Verdict.PASS
    assert "real hardware" in run_cases([HW], {}, HEAD)[0].reasons[0]


def test_reports():
    rs = [CaseResult("A", "perf", Verdict.PASS), CaseResult("B", "soak", Verdict.FAIL, ("x|y",))]
    doc = to_json(rs, HEAD)
    assert doc["overall"] == "fail" and doc["counts"] == {"pass": 1, "fail": 1, "blocked": 0}
    md = to_markdown(rs, HEAD)
    assert "**FAIL**" in md and "x\\|y" in md and md.count("\n| ") == 3


def test_cli_shipped_cases_blocked_without_evidence(tmp_path, capsys):
    rc = main(["--head", HEAD, "--evidence", str(tmp_path / "none")])
    doc = json.loads(capsys.readouterr().out)
    assert rc == 2 and doc["overall"] == "blocked"
    assert doc["counts"]["pass"] == 0 and len(doc["results"]) == len(list(DEFAULT_CASES.glob("*.json")))


def test_cli_pass_fail_schema_codes(tmp_path, write_evidence):
    cases = tmp_path / "cases"; cases.mkdir()
    (cases / "p.json").write_text(json.dumps({"id": "GFM-PERF-77", "gate": "perf", "title": "t",
        "todo_ref": "P3", "severity": "sev2", "params": {"metric": "m", "budgets_ms": {"p95": 10}, "min_samples": 3}}))
    write_evidence("GFM-PERF-77", {"samples_ms": [1, 2, 3]})
    out = tmp_path / "r.md"
    assert main(["--head", HEAD, "--cases", str(cases), "--evidence", str(write_evidence.dir),
                 "--format", "md", "--out", str(out)]) == 0
    assert "**PASS**" in out.read_text()
    write_evidence("GFM-PERF-77", {"samples_ms": [100, 200, 300]})
    assert main(["--head", HEAD, "--cases", str(cases), "--evidence", str(write_evidence.dir), "--out", str(out)]) == 1
    (cases / "bad.json").write_text("{}")
    assert main(["--head", HEAD, "--cases", str(cases), "--evidence", str(write_evidence.dir)]) == 3
