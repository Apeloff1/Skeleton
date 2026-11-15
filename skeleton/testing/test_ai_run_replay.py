"""#807 B072: AI-run replay evidence with perf gates (frame/alloc/load)."""
from __future__ import annotations

import hashlib
import json

import pytest

from skeleton.quality.deterministic_time import DeterministicClock
from skeleton.quality.ai_run_replay import (
    AiRunRecorder,
    AiRunReplayError,
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


def test_harness_duration_and_ai_perf_gates_use_shared_replay_with_explicit_clock() -> None:
    tape = ReplayTape()
    tape.append("tick", {"n": 1})
    manifest = load_manifest({
        "schema": EVIDENCE_SCHEMA, "scenario_id": "perf-gate-001", "kind": "performance",
        "source": "cognition.tape", "seed": 1, "max_runs": 2, "time_budget_ms": 1.0,
        "trace": tape.export(), "expected_duration_ms": 10.0, "observed_duration_ms": [10.0],
        "tolerances": {"duration_ms": 0.0, "duration_rel": 0.0},
    })
    ok = run_harness(manifest, clock=DeterministicClock(frozen=True))
    assert ok.verdict is Verdict.PASS
    assert ok.envelope["within"] is True
    assert verify_evidence(ok.to_mapping()).verdict is Verdict.PASS
    bad = run_harness(manifest, observed_duration_ms=[20.0], clock=DeterministicClock(frozen=True))
    assert bad.verdict is Verdict.FAIL and "performance envelope exceeded" in bad.reasons
    budgets = PerfBudgets(frame_ms=16.667, load_ms=500.0)
    assert evaluate_perf_against_budgets(PerfObservation(frame_ms=(16.0,), load_ms=(400.0,)), budgets)["within"]
    result = evaluate_perf_against_budgets(PerfObservation(frame_ms=(20.0,), load_ms=(400.0,)), budgets)
    assert not result["within"] and "frame_ms budget exceeded" in result["reasons"]


def _reseal(document):
    body = {key: value for key, value in document.items() if key != "digest"}
    document["digest"] = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return document


@pytest.mark.parametrize("patch", [
    {"events": []}, {"perf": []}, {"budgets": "bad"}, {"seed": True},
    {"run_id": ""}, {"unexpected": 1}, {"perf": {"frame_ms": [True]}},
])
def test_resealed_malformed_evidence_is_corrupt(patch) -> None:
    candidate = _reseal({**_run(), **patch})
    assert replay_ai_run(_run(), candidate)["verdict"] == "CORRUPT"


def test_seed_change_is_not_equivalent_even_when_events_match() -> None:
    candidate = _reseal({**_run(), "seed": 8})
    result = replay_ai_run(_run(), candidate)
    assert result["verdict"] == "FAIL"
    assert "replay metadata mismatch" in result["reasons"]


def test_caller_cannot_override_logical_timestamp() -> None:
    with pytest.raises(AiRunReplayError, match="reserved timestamp"):
        record_scripted_ai_run("run", [{"kind": "act", "t_ms": 999}])


def test_recorded_nested_payload_and_exports_are_detached() -> None:
    recorder = AiRunRecorder("owner")
    original = {"nested": {"value": [1]}}
    recorder.record("act", original)
    original["nested"]["value"].append(2)
    first = recorder.export()
    assert first["events"][0]["payload"]["nested"]["value"] == [1]
    first["events"][0]["payload"]["nested"]["value"].append(3)
    assert recorder.export()["events"][0]["payload"]["nested"]["value"] == [1]


@pytest.mark.parametrize("payload", [{1: "alias"}, {"x": float("nan")}, {"x": object()}])
def test_invalid_payload_never_advances_the_recorder(payload) -> None:
    recorder = AiRunRecorder("owner")
    with pytest.raises(AiRunReplayError):
        recorder.record("act", payload)
    assert recorder.clock.now_ms() == 0.0
    assert not recorder.tape.events


def test_failed_observation_does_not_append_partial_samples() -> None:
    recorder = AiRunRecorder("owner")
    with pytest.raises(AiRunReplayError):
        recorder.observe(frame_ms=12.0, alloc_bytes=-1)
    assert recorder.observation() == PerfObservation()


def test_loaded_replay_does_not_alias_input_document() -> None:
    document = _run()
    tape, _, _ = load_ai_run(document)
    document["events"][0]["payload"]["npc"] = "mutated"
    assert tape.events[0].payload["npc"] == "guard"
    assert tape.verify()


def test_unbounded_and_cyclic_replay_payload_rejected() -> None:
    recorder = AiRunRecorder("owner")
    cyclic = {}
    cyclic["self"] = cyclic
    with pytest.raises(AiRunReplayError):
        recorder.record("act", cyclic)
    with pytest.raises(AiRunReplayError):
        recorder.record("act", {"text": "x" * (16 * 1024 * 1024 + 1)})
    assert not recorder.tape.events


def test_cumulative_tape_admission_rejects_before_logical_clock_advances(monkeypatch):
    from skeleton.quality import ai_run_replay as replay
    monkeypatch.setattr(replay, "_MAX_RECORDED_EVENT_BYTES", 1000)
    recorder = AiRunRecorder("bounded")
    recorder.record("act", {"text": "a" * 400})
    before = recorder.export()
    clock = recorder.clock.now_ms()
    with pytest.raises(AiRunReplayError, match="cumulative replay event byte budget"):
        recorder.record("act", {"text": "b" * 400})
    assert recorder.clock.now_ms() == clock
    assert recorder.export() == before


def test_escaped_content_is_counted_before_serialization(monkeypatch):
    from skeleton.quality import ai_run_replay as replay
    monkeypatch.setattr(replay, "_MAX_JSON_BYTES", 1024)
    with pytest.raises(AiRunReplayError, match="JSON text exceeds bounds"):
        replay._canonical_bytes({"text": "界" * 300})


@pytest.mark.parametrize("bad", [True, -1, float("inf"), float("nan"), 10**400, "10"])
def test_direct_performance_construction_rejects_invalid_values(bad):
    with pytest.raises(AiRunReplayError):
        PerfBudgets(frame_ms=bad)
    with pytest.raises(AiRunReplayError):
        PerfObservation(frame_ms=(bad,))


def test_direct_performance_observation_detaches_mutable_input():
    source = [1.0]
    observation = PerfObservation(frame_ms=source)
    source.append(999.0)
    assert observation.frame_ms == (1.0,)


def test_event_kind_bound_is_transactional():
    recorder = AiRunRecorder("bounded")
    with pytest.raises(AiRunReplayError, match="event kind"):
        recorder.record("x" * 129, {})
    assert recorder.clock.now_ms() == 0
    assert not recorder.tape.events


@pytest.mark.parametrize("perf", [False, [], {"unexpected": 1}])
def test_scripted_run_rejects_invalid_performance_shape(perf):
    with pytest.raises(AiRunReplayError, match="performance fields"):
        record_scripted_ai_run("bounded", [{"kind": "act", "perf": perf}])
