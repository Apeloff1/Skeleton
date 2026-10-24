"""#807 B072: AI-run replay evidence with perf gates (frame/alloc/load)."""
from __future__ import annotations

from skeleton.quality.ai_run_replay import (
    SCHEMA_ID,
    PerfBudgets,
    PerfObservation,
    evaluate_perf_against_budgets,
    load_ai_run,
    record_scripted_ai_run,
    replay_ai_run,
)
from skeleton.quality.replay_evidence import (
    SCHEMA_ID as EVIDENCE_SCHEMA,
    DeterministicClock,
    ReplayTape,
    Verdict,
    load_manifest,
    run_harness,
    verify_evidence,
)

BUDGETS = PerfBudgets(frame_ms=16.667, alloc_bytes=4096, load_ms=500)
STEPS = [
    {"kind": "perceive", "npc": "guard", "perf": {"frame_ms": 12.0, "alloc_bytes": 1024, "load_ms": 120}},
    {"kind": "decide", "action": "patrol", "perf": {"frame_ms": 14.0, "alloc_bytes": 2048}},
    {"kind": "act", "action": "patrol", "perf": {"frame_ms": 15.5}},
]


def _run(steps=STEPS, budgets=BUDGETS):
    return record_scripted_ai_run("ai-run-1", steps, seed=7, budgets=budgets)


def test_recording_is_deterministic_and_uses_cognition_tape() -> None:
    first, second = _run(), _run()
    assert first == second
    assert first["schema"] == SCHEMA_ID
    tape, _, _ = load_ai_run(first)
    assert isinstance(tape, ReplayTape) and tape.verify()
    assert [e.payload["t_ms"] for e in tape.events] == [16.667, 33.334, 50.001]


def test_identical_runs_pass() -> None:
    result = replay_ai_run(_run(), _run())
    assert result["verdict"] == "PASS" and result["divergence"] is None


def test_divergent_decision_fails_with_sequence() -> None:
    changed = [dict(s) for s in STEPS]
    changed[1] = {**changed[1], "action": "flee"}
    result = replay_ai_run(_run(), _run(changed))
    assert result["verdict"] == "FAIL" and result["divergence"] == 1


def test_frame_budget_regression_fails() -> None:
    slow = [dict(s) for s in STEPS]
    slow[2] = {"kind": "act", "action": "patrol", "perf": {"frame_ms": 33.0}}
    result = replay_ai_run(_run(), _run(slow))
    assert result["verdict"] == "FAIL"
    assert "frame_ms budget exceeded" in result["reasons"]


def test_missing_budgeted_samples_fail_closed() -> None:
    env = evaluate_perf_against_budgets(PerfObservation(frame_ms=(10.0,)), BUDGETS)
    assert env["within"] is False
    assert "missing load_ms observations" in env["reasons"]
    assert "missing alloc_bytes observations" in env["reasons"]


def test_tampered_run_is_corrupt() -> None:
    doc = _run()
    doc["events"][0]["payload"]["npc"] = "thief"
    result = replay_ai_run(_run(), doc)
    assert result["verdict"] == "CORRUPT" and result["passed"] is False


def test_harness_perf_subenvelope_and_default_deterministic_clock() -> None:
    tape = ReplayTape()
    tape.append("tick", {"n": 1})
    manifest = load_manifest({
        "schema": EVIDENCE_SCHEMA, "scenario_id": "perf-gate-001", "kind": "performance",
        "source": "cognition.tape", "seed": 1, "max_runs": 2, "time_budget_ms": 1.0,
        "trace": tape.export(), "expected_duration_ms": 10.0, "observed_duration_ms": [10.0],
        "tolerances": {"duration_ms": 0.0, "duration_rel": 0.0, "frame_ms": 16.667, "load_ms": 500.0},
    })
    ok = run_harness(manifest, observed_perf={"frame_ms": [16.0], "load_ms": [400.0]})
    assert ok.verdict is Verdict.PASS  # deterministic default clock: no wall-clock timeout
    assert ok.envelope["perf"]["within"] is True
    assert verify_evidence(ok.to_mapping()).verdict is Verdict.PASS
    bad = run_harness(manifest, observed_perf={"frame_ms": [20.0], "load_ms": [400.0]})
    assert bad.verdict is Verdict.FAIL and "perf budget exceeded" in bad.reasons
    assert callable(DeterministicClock())
