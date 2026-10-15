"""Coverage-guided situational rehearsal, counterfactual auditing and retraining drafts.

Runs the real deterministic Jeeves cinematic simulation, then applies explicit
bounded *risk proxy* models to its observed per-frame state. Weather, stealth,
noise and crowd are scenario stressors, NOT fluid dynamics, acoustic rendering,
NPC inference or established model improvement.

The scheduler spends an explicit simulation budget: stratified coverage first,
then risk-guided local perturbations, and immutable source-paired comparisons.
Only quarantined adjudication drafts leave this module, never serving weights.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor
from hashlib import sha256
from multiprocessing import get_context
from pathlib import Path
import json
import os
import sys

from .jeeves_cinematic_simulation import (
    CinematicSimError, SimulationController, _bounded_int, _hash, _json,
    _read_json, _write_new, _write_new_bytes, validate_scene, variation_controls,
    receipt_from_controller,
)

SCHEMA = "skeleton.jeeves.adaptive_sim_campaign.v1"
SCENARIO = "skeleton.jeeves.situational_scenario.v1"
SITUATIONS = ("dialogue", "pursuit", "stealth", "rescue", "combat", "exploration")
WEATHER = ("clear", "fog", "rain", "snow", "storm")
LIGHT = ("day", "dusk", "night", "artificial")
ATTACKS = ("none", "low_visibility", "high_wind", "distracting_noise",
           "crowd_occlusion", "low_friction", "load_spike", "camera_whip")
MAX_CASES = 256
MAX_POOL = 1024
MAX_TOTAL_FRAMES = 180000

# Explicitly synthetic boundary environments. Units: millimeters, millimeters
# per second, integer percentages. No claims of photorealistic weather physics.
ENVIRONMENTS = {
    "clear": (100000, 800, 8, 95),
    "fog": (1800, 500, 25, 78),
    "rain": (9000, 6000, 48, 56),
    "snow": (6500, 3800, 28, 42),
    "storm": (2300, 18000, 75, 33),
}
ATTACK_BIAS = {
    "none": (0, 0, 0, 0, 0),
    "low_visibility": (-1450, 0, 0, 0, 0),
    "high_wind": (0, 14000, 0, 0, 0),
    "distracting_noise": (0, 0, 65, 0, 0),
    "crowd_occlusion": (0, 0, 0, 90, 0),
    "low_friction": (0, 0, 0, 0, -65),
    "load_spike": (0, 0, 0, 0, 0),
    "camera_whip": (0, 0, 0, 0, 0),
}


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise CinematicSimError("adaptive Jeeves sim: " + message)


def _scenario(situation: str, weather: str, light: str, attack: str,
              crowd_pct: int, camera_yaw: int, pan_rate: int,
              mass_delta: int, apparel_drag: int, seed: int) -> dict:
    _require(situation in SITUATIONS and weather in WEATHER and light in LIGHT
             and attack in ATTACKS, "unknown situation, environment or attack")
    _bounded_int(crowd_pct, 0, 100, "crowd density")
    _bounded_int(camera_yaw, -60, 60, "camera yaw")
    _bounded_int(pan_rate, 40, 160, "pan speed")
    _bounded_int(mass_delta, -1000, 1000, "item mass")
    _bounded_int(apparel_drag, -30, 30, "outfit drag")
    _bounded_int(seed, 0, 2**31-1, "source seed")
    value = {
        "schema_version": SCENARIO, "situation": situation,
        "weather": weather, "lighting": light, "attack": attack,
        "crowd_pct": crowd_pct, "yaw_offset_deg": camera_yaw,
        "pan_rate_pct": pan_rate, "item_mass_delta_g": mass_delta,
        "apparel_drag_delta_pct": apparel_drag, "seed": seed,
    }
    value["scenario_id"] = _hash(value)
    return value


def validate_scenario(value: dict) -> dict:
    _require(type(value) is dict and set(value) == {
        "schema_version", "situation", "weather", "lighting", "attack",
        "crowd_pct", "yaw_offset_deg", "pan_rate_pct", "item_mass_delta_g",
        "apparel_drag_delta_pct", "seed", "scenario_id",
    } and value["schema_version"] == SCENARIO,
             "unknown scenario schema")
    expected = _scenario(value["situation"], value["weather"], value["lighting"],
                         value["attack"], value["crowd_pct"], value["yaw_offset_deg"],
                         value["pan_rate_pct"], value["item_mass_delta_g"],
                         value["apparel_drag_delta_pct"], value["seed"])
    _require(_json(expected) == _json(value), "scenario parameter digest changed")
    return expected


def draft_scenarios(scene: dict, *, budget: int = 48, seed: int = 0) -> tuple[dict, ...]:
    """Stratified, deterministic situation/environment/attack rehearsal plan."""
    validate_scene(scene)
    _bounded_int(budget, 2, MAX_CASES, "adaptive campaign budget")
    _bounded_int(seed, 0, 2**31-1, "campaign seed")
    combinations = []
    for i in range(min(MAX_POOL, max(3*budget, 64))):
        situation = SITUATIONS[(i + seed) % len(SITUATIONS)]
        weather = WEATHER[(i//len(SITUATIONS) + i//17) % len(WEATHER)]
        light = LIGHT[(i//7 + i//31) % len(LIGHT)]
        attack = ATTACKS[(i//3 + i//19) % len(ATTACKS)]
        # Parameter edge coverage, not random synthetically "successful" results.
        yaw = (-60, -30, 0, 30, 60)[i % 5]
        pan = (40, 75, 100, 125, 160)[(i//5) % 5]
        mass = (-1000, 0, 1000)[(i//11) % 3]
        drag = (-30, 0, 30)[(i//13) % 3]
        crowd = (0, 25, 55, 85, 100)[(i//11 + i//5) % 5]
        case = _scenario(situation, weather, light, attack, crowd, yaw, pan,
                         mass, drag, seed)
        combinations.append(case)
    # Greedy max-coverage over tuple interactions: situation × environment,
    # environment × attack, lighting × situation, and control boundaries.
    selected, observed = [], set()
    while len(selected) < budget:
        def gain(case):
            features = _features(case)
            new = len(features - observed)
            # Reproducible seed tie-break, no cross-run stochastic drift.
            return (new, -len(features & observed), _hash(case))
        remaining = [row for row in combinations
                     if row["scenario_id"] not in {x["scenario_id"] for x in selected}]
        if not remaining:
            break
        chosen = max(remaining, key=gain)
        selected.append(chosen)
        observed |= _features(chosen)
    _require(len(selected) == budget and len({r["scenario_id"] for r in selected}) == budget,
             "insufficient distinct scenario drafts")
    return tuple(selected)


def _features(case: dict) -> set[str]:
    return {
        "situation:" + case["situation"], "weather:" + case["weather"],
        "lighting:" + case["lighting"], "attack:" + case["attack"],
        "situation_weather:" + case["situation"] + ":" + case["weather"],
        "weather_attack:" + case["weather"] + ":" + case["attack"],
        "situation_lighting:" + case["situation"] + ":" + case["lighting"],
        "yaw:" + str(case["yaw_offset_deg"]),
        "pan:" + str(case["pan_rate_pct"]),
        "mass:" + str(case["item_mass_delta_g"]),
        "drag:" + str(case["apparel_drag_delta_pct"]),
        "crowd:" + str(case["crowd_pct"]),
    }


def _controls(case: dict) -> dict:
    yaw = case["yaw_offset_deg"]
    pan = case["pan_rate_pct"]
    mass = case["item_mass_delta_g"]
    drag = case["apparel_drag_delta_pct"]
    if case["attack"] == "camera_whip":
        pan = min(160, pan + 35)
        yaw = max(-60, min(60, yaw + 20))
    if case["attack"] == "load_spike":
        mass = min(1000, mass + 750)
        drag = min(30, drag + 10)
    return variation_controls(offsets=(yaw,), pan_rates=(pan,),
            item_mass_deltas=(mass,), apparel_drag_deltas=(drag,),
            seeds=(case["seed"],))[0]


def _environment(case: dict) -> dict:
    visibility, wind, noise, friction = ENVIRONMENTS[case["weather"]]
    v_bias, w_bias, n_bias, crowd_bias, friction_bias = ATTACK_BIAS[case["attack"]]
    light_bias = {"day": 100, "dusk": 55, "night": 12, "artificial": 85}[case["lighting"]]
    return {"visibility_mm": max(300, visibility + v_bias),
            "wind_mm_s": min(40000, wind + w_bias),
            "noise_pct": min(100, noise + n_bias),
            "friction_pct": max(0, friction + friction_bias),
            "ambient_light_pct": light_bias,
            "crowd_pct": min(100, case["crowd_pct"] + crowd_bias)}


def _risk(frame: dict, case: dict, env: dict) -> tuple[str, ...]:
    """Deterministic observable risk proxy; NOT a rendered/physical simulator."""
    defects = []
    if frame["focus_distance_mm"] > env["visibility_mm"]:
        defects.append("visibility_loss")
    if env["ambient_light_pct"] < 20 and frame["fov_deg"] < 70:
        defects.append("night_low_light_readability")
    if env["wind_mm_s"] >= 17000 and frame["mobility_pct"] < 75:
        defects.append("wind_apparel_stability")
    if env["noise_pct"] >= 75 and frame["dialogue"]:
        defects.append("dialogue_masking_risk")
    if env["crowd_pct"] >= 85 and frame["camera"] in ("closeup", "tracking", "pan_to"):
        defects.append("crowd_target_occlusion")
    if env["friction_pct"] <= 45 and frame["camera"] in ("dolly", "tracking", "crane"):
        defects.append("low_friction_camera_rig")
    if case["situation"] in ("pursuit", "rescue", "combat") and frame["mobility_pct"] < 50:
        defects.append("time_critical_mobility")
    if case["situation"] == "stealth" and (
        env["ambient_light_pct"] >= 85 or env["crowd_pct"] >= 85):
        defects.append("stealth_exposure")
    if case["situation"] == "dialogue" and env["noise_pct"] >= 65 and frame["dialogue"]:
        defects.append("conversation_intelligibility")
    if case["situation"] == "pursuit" and case["pan_rate_pct"] <= 75:
        defects.append("pursuit_lagging_camera")
    return tuple(defects)


def _run_case(scene: dict, case: dict, frame_ms: int) -> dict:
    validate_scenario(case)
    controller = SimulationController(scene, _controls(case), frame_ms=frame_ms)
    frames = controller.run()
    receipt = receipt_from_controller(controller)
    _require(receipt["audit"]["reverse"]["passed"] is True,
             "source-derived reverse audit failure")
    env = _environment(case)
    counts: dict[str, int] = {}
    first: dict[str, dict] = {}
    for frame in frames:
        for defect in (*frame["issues"], *_risk(frame, case, env)):
            counts[defect] = counts.get(defect, 0) + 1
            first.setdefault(defect, {"frame": frame["frame"],
                                      "tick_ms": frame["tick_ms"],
                                      "observation_sha256": frame["digest"]})
    severity = sum(min(n, 12) for n in counts.values())
    return {
        "schema_version": "skeleton.jeeves.adaptive_case_receipt.v1",
        "scenario": case, "environment": env,
        "controls": dict(controller.controls),
        "source_digest": receipt["source_digest"],
        "trace_digest": receipt["forward_head_digest"],
        "frames_executed": receipt["frames_executed"],
        "reverse_audit_passed": True,
        "risk_counts": counts, "first_evidence": first,
        "risk_severity": severity, "source_replay_receipt": receipt["receipt_sha256"],
        "rendered_environment": False, "independent_model_training": False,
    }


def _baseline(scene: dict, seed: int, frame_ms: int) -> dict:
    baseline = _scenario("dialogue", "clear", "day", "none", 0, 0, 100, 0, 0, seed)
    return _run_case(scene, baseline, frame_ms)


def _targeted(case: dict, signal: str, generation: int) -> dict:
    """Produce one minimal, deterministic counterfactual around a found risk."""
    fields = {k: v for k, v in case.items() if k not in ("schema_version", "scenario_id")}
    if "visibility" in signal or "occlusion" in signal:
        fields["weather"] = "fog" if fields["weather"] != "fog" else "storm"
        fields["attack"] = "low_visibility"
    elif "camera" in signal or "pan" in signal:
        fields["attack"] = "camera_whip"
        fields["pan_rate_pct"] = min(160, fields["pan_rate_pct"]+20)
    elif "apparel" in signal or "mobility" in signal or "wind" in signal:
        fields["weather"] = "storm"
        fields["apparel_drag_delta_pct"] = min(30, fields["apparel_drag_delta_pct"] + 10)
    elif "dialogue" in signal or "intelligibility" in signal:
        fields["attack"] = "distracting_noise"
        fields["situation"] = "dialogue"
    else:
        fields["lighting"] = "night" if generation % 2 else "dusk"
        fields["crowd_pct"] = min(100, fields["crowd_pct"]+25)
    return _scenario(fields["situation"], fields["weather"], fields["lighting"],
                     fields["attack"], fields["crowd_pct"], fields["yaw_offset_deg"],
                     fields["pan_rate_pct"], fields["item_mass_delta_g"],
                     fields["apparel_drag_delta_pct"], fields["seed"])


def _execute(scene: dict, cases: tuple[dict, ...], frame_ms: int, workers: int):
    _require(len(cases) <= MAX_CASES, "active batch exceeds worker admission")
    if workers == 1:
        return [_run_case(scene, case, frame_ms) for case in cases]
    with ProcessPoolExecutor(max_workers=workers, mp_context=get_context("spawn")) as pool:
        futures = [pool.submit(_run_case, scene, case, frame_ms) for case in cases]
        return [job.result() for job in futures]


def run_campaign(scene: dict, *, budget: int = 24, seed: int = 0,
                 workers: int = 1, frame_ms: int = 100) -> dict:
    """Stratified first pass, then risk-focused feedback without data inflation."""
    validated = validate_scene(scene)
    _bounded_int(budget, 4, MAX_CASES, "campaign budget")
    _bounded_int(seed, 0, 2**31-1, "campaign seed")
    _bounded_int(workers, 1, 8, "workers")
    _bounded_int(frame_ms, 25, 250, "frame interval")
    expected_frames = (validated["total_ms"] + frame_ms - 1)//frame_ms+1
    _require((budget+1)*expected_frames <= MAX_TOTAL_FRAMES,
             "campaign aggregate frame budget exceeded")
    initial_count = max(2, budget//2)
    first = draft_scenarios(scene, budget=initial_count, seed=seed)
    baseline = _baseline(scene, seed, frame_ms)
    first_results = _execute(scene, first, frame_ms, workers)
    seen = {row["scenario"]["scenario_id"] for row in first_results}
    # The second stage depends on measured first-stage failures, not a canned
    # cartesian multiplication of unobserved edge cases.
    priority = sorted(first_results, key=lambda row: (
        -row["risk_severity"], -len(row["risk_counts"]),
        row["scenario"]["scenario_id"]))
    followup = []
    for generation in range(1, 9):
        for result in priority:
            if len(followup) >= budget - initial_count:
                break
            signals = sorted(result["risk_counts"],
                             key=lambda k: (-result["risk_counts"][k], k))
            candidate = _targeted(result["scenario"],
                                  signals[(generation-1) % len(signals)] if signals else "coverage",
                                  generation)
            if candidate["scenario_id"] not in seen:
                seen.add(candidate["scenario_id"])
                followup.append(candidate)
        if len(followup) >= budget - initial_count:
            break
    if len(followup) < budget - initial_count:
        for candidate in draft_scenarios(scene, budget=budget, seed=seed+1):
            if candidate["scenario_id"] not in seen:
                seen.add(candidate["scenario_id"])
                followup.append(candidate)
            if len(followup) == budget-initial_count:
                break
    _require(len(followup) == budget-initial_count, "adaptive follow-up coverage exhausted")
    second_results = _execute(scene, tuple(followup), frame_ms, workers)
    rows = first_results + second_results
    _require(len(rows) == budget and all(row["reverse_audit_passed"] for row in rows),
             "simulation quota or reverse integrity failure")
    covered = set().union(*(_features(row["scenario"]) for row in rows))
    baseline_risks = baseline["risk_counts"]
    seen_traces = {baseline["trace_digest"]}
    distinct = 0
    for row in rows:
        if row["trace_digest"] not in seen_traces:
            seen_traces.add(row["trace_digest"])
            distinct += 1
        row["delta_risk_severity_vs_baseline"] = row["risk_severity"] - baseline["risk_severity"]
        row["new_failure_families_vs_baseline"] = sorted(
            set(row["risk_counts"]) - set(baseline_risks))
    distribution = {}
    for row in rows:
        for family in row["risk_counts"]:
            distribution[family] = distribution.get(family, 0)+1
    report = {
        "schema_version": SCHEMA, "source_project_id": validated["project"],
        "source_digest": validated["source_digest"], "budget_requested": budget,
        "simulations_executed": budget+1, "baseline_runs": 1,
        "stratified_runs": len(first_results), "feedback_guided_runs": len(second_results),
        "parallel_workers_requested": workers, "seed": seed, "frame_ms": frame_ms,
        "forward_observations": sum(row["frames_executed"] for row in rows)+baseline["frames_executed"],
        "reverse_observations": sum(row["frames_executed"] for row in rows)+baseline["frames_executed"],
        "unique_controlled_trace_digests": len(seen_traces),
        "unique_camera_traces_excluding_baseline": distinct,
        "source_project_independence_count": 1,
        "risk_families_observed": sorted(distribution),
        "risk_family_frequency": distribution,
        "coverage_features": sorted(covered),
        "coverage_feature_count": len(covered),
        "highest_risk_cases": [row["scenario"]["scenario_id"] for row in sorted(
            rows, key=lambda x: (-x["risk_severity"], x["scenario"]["scenario_id"]))[:8]],
        "baseline": baseline, "cases": rows,
        "rights_reviewed_by_operator": True,
        "candidate_adjudication": "quarantined",
        "trained_candidate_weights": False, "serving_model_mutated": False,
        "environmental_rendering_performed": False,
        "independent_model_quality_benchmark_complete": False,
    }
    report["receipt_sha256"] = _hash(report)
    return report


def verify_campaign(report: dict) -> dict:
    """Verify report consistency and counts; not a substitute for raw replay."""
    _require(type(report) is dict and report.get("schema_version") == SCHEMA,
             "unknown campaign receipt schema")
    _require(report.get("receipt_sha256") == _hash({
        k: v for k, v in report.items() if k != "receipt_sha256"
    }), "campaign receipt SHA mismatch")
    rows = report.get("cases")
    _require(type(rows) is list and len(rows) == report["budget_requested"] and
             report["simulations_executed"] == len(rows)+1,
             "campaign run counts changed")
    baseline = report["baseline"]
    _require(all(row["source_digest"] == baseline["source_digest"] and
                 row["reverse_audit_passed"] is True for row in rows),
             "cross-source receipt or reverse-integrity drift")
    _require(report["forward_observations"] == report["reverse_observations"] ==
             sum(row["frames_executed"] for row in rows)+baseline["frames_executed"],
             "forward/reverse observation-count laundering")
    identities = [row["scenario"]["scenario_id"] for row in rows]
    _require(len(set(identities)) == len(identities) and
             all(validate_scenario(row["scenario"]) for row in rows),
             "duplicate or forged scenario identity")
    _require(report["trained_candidate_weights"] is False and
             report["serving_model_mutated"] is False,
             "unverified model training promotion state")
    return {"status": "verified_quarantined_simulation_campaign",
            "count": len(rows), "reverse_audit_complete": True,
            "model_training_proven": False}


def retraining_drafts(report: dict) -> tuple[dict, ...]:
    """Draft positive and negative reviewed-data prompts from real risk deltas.

    All pairs remain in the same source-project evidence group. A separate,
    human-verified supervision answer and rights approval are mandatory.
    """
    verify_campaign(report)
    output = []
    seen = set()
    for row in sorted(report["cases"], key=lambda x: (
        -x["risk_severity"], x["scenario"]["scenario_id"])):
        family = sorted(row["risk_counts"],
                        key=lambda k: (-row["risk_counts"][k], k))
        signature = _hash({"project": report["source_project_id"],
                           "trace": row["trace_digest"], "risks": family})
        if signature in seen:
            continue
        seen.add(signature)
        for perspective in ("situational_diagnosis", "counterfactual_repair",
                            "adversarial_edge_review"):
            target = {
                "situational_diagnosis": "Locate first evidence of failure and distinguish observed camera facts from environment proxy estimates.",
                "counterfactual_repair": "Propose one minimal permitted scene or control adjustment, then demand a fresh source-grounded verification run.",
                "adversarial_edge_review": "Challenge the diagnosis with a boundary case; do not infer a rendered scene or claim real-world physics.",
            }[perspective]
            output.append({
                "schema_version": "skeleton.jeeves.adaptive_retraining_draft.v1",
                "candidate_id": _hash({"signature": signature, "view": perspective}),
                "source_project_id": report["source_project_id"],
                "evidence_group": signature, "perspective": perspective,
                "prompt": target, "scenario": row["scenario"],
                "observed_risk_families": family,
                "first_evidence": row["first_evidence"],
                "risk_delta_vs_baseline": row["delta_risk_severity_vs_baseline"],
                "baseline_trace_sha256": report["baseline"]["trace_digest"],
                "candidate_trace_sha256": row["trace_digest"],
                "operator_rights_review_is_not_independent_legal_clearance": True,
                "review_status": "quarantined_needs_independent_label",
                "optimizer_eligible": False, "training_steps_executed": 0,
            })
    return tuple(output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", type=Path)
    parser.add_argument("--audit-report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--draft-output", type=Path)
    parser.add_argument("--budget", type=int, default=24)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--frame-ms", type=int, default=100)
    args = parser.parse_args(argv)
    try:
        if args.audit_report is not None:
            _require(args.scene is None and args.output is None,
                     "audit-only operation cannot start another simulation")
            report = _read_json(args.audit_report, 16*1024*1024)
        else:
            _require(args.scene is not None, "original rights-reviewed scene required")
            scene = _read_json(args.scene, 128*1024)
            report = run_campaign(scene, budget=args.budget, workers=args.workers,
                                  seed=args.seed, frame_ms=args.frame_ms)
            if args.output is not None:
                _write_new(args.output, report)
        verified = verify_campaign(report)
        if args.draft_output is not None:
            examples = retraining_drafts(report)
            _write_new_bytes(args.draft_output,
                             b"".join(_json(example)+b"\n" for example in examples))
            verified["quarantined_review_drafts"] = len(examples)
        print(json.dumps({**verified, "simulation_count": report["simulations_executed"],
                          "risk_families": report["risk_families_observed"],
                          "model_weights_trained": False}, sort_keys=True))
        return 0
    except (CinematicSimError, TypeError, ValueError, KeyError, OSError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:400],
                          "model_weights_trained": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
