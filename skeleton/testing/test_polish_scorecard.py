"""Quality rubric + polish scorecard tests (FE-facing forge polish payloads)."""
from __future__ import annotations

from skeleton.forge.forge_quality import PRODUCTION_THRESHOLD, evaluate
from skeleton.forge.polish_scorecard import (
    empty_scorecard,
    gate_chips,
    phase_gate_scorecard,
    progress_from_polish_result,
    round_history,
    scorecard_batch,
    scorecard_for_item,
)
from skeleton.forge.quality_rubric import (
    GATE_WEIGHTS,
    compare_rubrics,
    fidelity_band,
    grade_band,
    production_tier,
    rubric_for_verdict,
    suggest_next_actions,
    weighted_gate_score,
)


def _good_item(**overrides):
    base = {
        "id": "artefact-1",
        "grade": 5,
        "stage": "hub",
        "code": "export const behaviour = { tick() {} };\n",
        "skin": {"fidelity": 1.0, "era": "roguelike"},
        "placement": {"region": "overworld"},
        "era": "roguelike",
    }
    base.update(overrides)
    return base


def test_gate_weights_sum_to_one():
    assert abs(sum(GATE_WEIGHTS.values()) - 1.0) < 1e-9


def test_bands_and_tiers():
    assert grade_band(0) == "prototype"
    assert grade_band(7) == "production"
    assert fidelity_band(0.72) == "staging"
    assert fidelity_band(1.0) == "aaa"
    assert fidelity_band("bad") == "stub"
    assert production_tier(PRODUCTION_THRESHOLD) == "production"
    assert production_tier(70) == "staging"
    assert production_tier(10) == "reject"


def test_weighted_score_skips_not_applicable_gates():
    gates = [
        {"name": "behaviour_code", "passed": True},
        {"name": "fidelity_floor", "passed": True, "applicable": False},
        {"name": "gdd_parity", "passed": False},
    ]
    # Only behaviour (0.22) and gdd (0.15) count.
    assert weighted_gate_score(gates) == round(0.22 / 0.37, 4)
    assert weighted_gate_score([]) == 0.0


def test_rubric_orders_failures_by_severity():
    item = _good_item(grade=0, placement={"region": "nowhere"}, stage="missing")
    verdict = evaluate(item, stage_floor_grade=1, gdd_stages={"hub"}, regions=["overworld"])
    rubric = rubric_for_verdict(verdict, grade=0, fidelity=1.0)
    assert rubric["failed_ordered"][0] == "grade_escalation"
    assert rubric["critical_failures"] == ["grade_escalation"]
    assert set(rubric["failed_ordered"]) == {"grade_escalation", "placement_valid", "gdd_parity"}
    actions = suggest_next_actions(rubric)
    assert [a["action"] for a in actions] == ["raise_grade", "place_region", "align_stage"]


def test_rubric_keeps_zero_production_score():
    rubric = rubric_for_verdict({"gates": [], "production_score": 0}, grade=5, fidelity=1.0)
    assert rubric["production_score"] == 0
    assert rubric["production_tier"] == "reject"


def test_content_artefact_is_told_to_declare_signals():
    item = {"title": "t", "files": {"a.gd": "extends Node\nfunc _ready():\n\tpass\n"}}
    card = scorecard_for_item(item)
    assert card["passed"] is True
    assert card["production_ready"] is False
    assert {"grade_escalation", "fidelity_floor"} <= set(card["rubric"]["not_applicable"])
    assert card["next_actions"][0]["action"] == "declare_signals"
    tones = {c["id"]: c["tone"] for c in card["chips"]}
    assert tones["fidelity_floor"] == "muted"
    assert tones["behaviour_code"] == "good"


def test_scorecard_for_production_item():
    card = scorecard_for_item(_good_item(), gdd_stages={"hub"}, regions=["overworld"])
    assert card["production_ready"] is True
    assert card["repair_eligible"] is False
    assert card["era"] == "roguelike"
    assert card["region"] == "overworld"
    assert card["next_actions"] == []
    assert all(c["tone"] == "good" for c in card["chips"])


def test_scorecard_era_prefers_explicit_then_skin():
    item = _good_item(skin={"fidelity": 1.0, "era": "roguelike"})
    item.pop("era")
    assert scorecard_for_item(item)["era"] == "roguelike"
    assert scorecard_for_item(item, era="roguelike")["era"] == "roguelike"
    plain = {"id": "x", "region": "r"}
    card = scorecard_for_item(plain)
    assert card["era"] is None and card["region"] == "r"


def test_batch_triage_counts_blocked_gates():
    items = [
        _good_item(id="a"),
        _good_item(id="b", placement={"region": "void"}),
        _good_item(id="c", placement={"region": "void"}, stage="nope"),
    ]
    batch = scorecard_batch(items, gdd_stages={"hub"}, regions=["overworld"])
    assert batch["count"] == 3
    assert batch["production_ready_count"] == 1
    assert batch["triage"][0] == {"gate": "placement_valid", "count": 2}
    assert {"gate": "gdd_parity", "count": 1} in batch["triage"]
    assert batch["all_production_ready"] is False
    assert scorecard_batch([])["all_production_ready"] is False


def test_round_history_accepts_both_shapes():
    trace = [{"round": 1}]
    assert round_history({"rounds": 1, "round_history": trace}) == trace
    assert round_history({"rounds": trace}) == trace
    assert round_history({"rounds": 2}) == []


def test_progress_from_polish_loop_result():
    result = {
        "ok": 0,
        "production_ready": False,
        "production_score": 80,
        "rounds": 2,
        "round_history": [
            {"round": 1, "actions": [{"gate": "x"}], "after": {"production_score": 80, "failed_gates": ["x"]}},
            {"round": 2, "actions": [], "after": {"production_score": 80, "failed_gates": ["x"]}},
        ],
        "quality": {"verdict": "rejected: x"},
    }
    prog = progress_from_polish_result(result)
    assert [s["status"] for s in prog["steps"]] == ["improved", "stalled"]
    assert prog["rounds_executed"] == 2
    assert prog["verdict"] == "rejected: x"


def test_compare_rubrics_tracks_cleared_and_regressed():
    before = {"production_score": 60, "failed_ordered": ["a", "b"], "production_tier": "draft"}
    after = {"production_score": 90, "failed_ordered": ["b", "c"], "production_tier": "staging"}
    d = compare_rubrics(before, after)
    assert d["score_delta"] == 30 and d["improved"] is True
    assert d["gates_cleared"] == ["a"]
    assert d["gates_regressed"] == ["c"]
    assert d["still_failing"] == ["b"]


def test_gate_chips_and_empty_scorecard():
    chips = gate_chips({"gates": [{"name": "gdd_parity", "passed": False}]})
    assert chips[0]["testID"] == "gate-chip-gdd_parity" and chips[0]["tone"] == "warn"
    empty = empty_scorecard(reason="loading")
    assert empty["empty"] is True and empty["empty_reason"] == "loading"
    assert empty["chips"] == [] and empty["production_ready"] is False


def test_phase_gate_scorecard_exposes_qa_band():
    card = phase_gate_scorecard({"era": "roguelike"}, {"forged": 0})
    assert card["kind"] == "phase-gate-scorecard"
    assert card["bands_total"] == len(card["chips"]) > 0
    assert card["qa_polish"]["band"] == "QA / Polish"
    assert card["all_gates_green"] is False
