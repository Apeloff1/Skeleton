#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "machine" / "project_self_improvement_1000.json"

MATURITY = [
    "planned","specified","implemented","integrated",
    "independently_verified","adversarially_qualified","signed_complete",
]
RANK = {state: i for i, state in enumerate(MATURITY)}

def validate(data: dict) -> list[str]:
    errors: list[str] = []
    levels = data.get("levels", [])
    strata = data.get("strata", [])
    waves = data.get("construction_waves", [])
    rel = data.get("relationship", {})
    idle = data.get("idle_activation", {})
    mirror = data.get("mirror_room_topology", {})
    resources = data.get("resource_governance", {})
    candidates = data.get("candidate_policy", {})
    inst = data.get("project_instantiation", {})
    completion = data.get("completion", {})

    if data.get("schema_version") != "skeleton.project_self_improvement_1000.v1":
        errors.append("unexpected schema_version")
    if len(levels) != 1000:
        errors.append(f"expected 1000 levels, got {len(levels)}")
    if len(strata) != 100:
        errors.append(f"expected 100 strata, got {len(strata)}")
    if len(waves) != 100:
        errors.append(f"expected 100 construction waves, got {len(waves)}")

    if rel.get("expands_top_level_volumes") is not False:
        errors.append("PSI-1000 must not expand top-level volumes")
    if rel.get("frozen_volume_range") != ["VOL-000", "VOL-420"]:
        errors.append("frozen volume range changed")
    if rel.get("range") != ["PSI1000-0001", "PSI1000-1000"]:
        errors.append("unexpected PSI-1000 identity range")
    if rel.get("total_levels") != 1000 or rel.get("strata") != 100 or rel.get("levels_per_stratum") != 10:
        errors.append("relationship cardinality mismatch")

    expected = [f"PSI1000-{i:04d}" for i in range(1, 1001)]
    if [x.get("id") for x in levels] != expected:
        errors.append("level IDs/order must be exactly PSI1000-0001..PSI1000-1000")

    for i, layer in enumerate(levels, start=1):
        lid = layer.get("id")
        expected_stratum = f"PSI-S{((i - 1)//10)+1:03d}"
        if layer.get("ordinal") != i:
            errors.append(f"{lid}: ordinal mismatch")
        if layer.get("stratum_id") != expected_stratum:
            errors.append(f"{lid}: stratum mismatch")
        if layer.get("stage") != ((i - 1) % 10) + 1:
            errors.append(f"{lid}: stage mismatch")
        if layer.get("maturity") not in RANK:
            errors.append(f"{lid}: invalid maturity")
        if not layer.get("mirror_room_contract") or not layer.get("acceptance_proof"):
            errors.append(f"{lid}: missing mirror-room/proof contract")
        if layer.get("idle_eligible") is not True:
            errors.append(f"{lid}: must be idle eligible")
        if layer.get("foreground_preemptible") is not True:
            errors.append(f"{lid}: must be foreground preemptible")
        if layer.get("production_mutation_allowed") is not False:
            errors.append(f"{lid}: cannot permit direct production mutation")
        if layer.get("project_scoped") is not True:
            errors.append(f"{lid}: must be project scoped")
        expected_la = f"L400-{((i - 1) % 400) + 1:03d}"
        expected_aa = f"A400-{((i - 1) % 400) + 1:03d}"
        if layer.get("linked_learning_layer") != expected_la:
            errors.append(f"{lid}: learning link mismatch")
        if layer.get("linked_adversarial_layer") != expected_aa:
            errors.append(f"{lid}: adversarial link mismatch")
        for dep in layer.get("depends_on", []):
            if dep not in expected[:i-1]:
                errors.append(f"{lid}: dependency {dep} is unknown or not earlier")
        if layer.get("complete") is True:
            if layer.get("maturity") != "signed_complete":
                errors.append(f"{lid}: complete without signed_complete maturity")
            if not layer.get("implementation_signed"):
                errors.append(f"{lid}: complete without implementation signature")
            if not layer.get("independent_verification_signed"):
                errors.append(f"{lid}: complete without independent verification signature")
            if not layer.get("evidence"):
                errors.append(f"{lid}: complete without evidence")

    for i, s in enumerate(strata, start=1):
        sid = f"PSI-S{i:03d}"
        if s.get("id") != sid or s.get("ordinal") != i:
            errors.append(f"stratum {i}: identity mismatch")
        if s.get("layer_range") != [f"PSI1000-{((i-1)*10)+1:04d}", f"PSI1000-{i*10:04d}"]:
            errors.append(f"{sid}: range mismatch")

    for i, w in enumerate(waves, start=1):
        wid = f"PSI-W{i:03d}"
        if w.get("id") != wid:
            errors.append(f"wave {i}: identity mismatch")
        expected_prev = None if i == 1 else f"PSI-W{i-1:03d}"
        if w.get("prerequisite_wave") != expected_prev:
            errors.append(f"{wid}: prerequisite mismatch")

    if idle.get("semantics") != "foreground-idle, not machine-idle":
        errors.append("idle semantics changed")
    if idle.get("activation") != "immediate when deterministic idle predicate becomes true":
        errors.append("idle activation must remain immediate")
    if not idle.get("idle_predicate") or not idle.get("preemption"):
        errors.append("idle predicate/preemption missing")
    if not idle.get("continuous_idle_rule"):
        errors.append("continuous idle rule missing")

    for key in ["proposer_room","challenger_room","role_reversal","verifier_room","archivist_plane","isolation","finality"]:
        if not mirror.get(key):
            errors.append(f"mirror room topology missing {key}")

    if resources.get("foreground_priority") != "absolute":
        errors.append("foreground priority must be absolute")
    if resources.get("cancellation_required") is not True:
        errors.append("cancellation must be required")
    if resources.get("no_unbounded_loop") is not True:
        errors.append("unbounded mirror-room loops forbidden")
    if not resources.get("per_epoch_required_budgets"):
        errors.append("per-epoch budgets required")

    if candidates.get("production_in_place_self_mutation") is not False:
        errors.append("production in-place self mutation must be false")
    if candidates.get("immutable_baseline_required") is not True:
        errors.append("immutable baseline required")
    if candidates.get("versioned_candidates_required") is not True:
        errors.append("versioned candidates required")
    if not candidates.get("promotion_requires"):
        errors.append("promotion requirements missing")

    if "independently for every project" not in inst.get("rule", ""):
        errors.append("per-project independent instantiation rule missing")
    if "deny-by-default" not in inst.get("cross_project_transfer", ""):
        errors.append("cross-project transfer must be deny-by-default")

    signed = sum(x.get("complete") is True for x in levels)
    if completion.get("template_levels") != 1000:
        errors.append("completion template level count mismatch")
    if completion.get("template_signed_complete") != signed:
        errors.append("template completion count mismatch")
    if completion.get("implementation_claim") is not False:
        errors.append("template must not claim implementation")
    if completion.get("global_project_qualification_claim") is not False:
        errors.append("template must not claim global project qualification")

    final = levels[-1] if levels else {}
    if final.get("id") != "PSI1000-1000":
        errors.append("finality identity must be PSI1000-1000")

    return errors

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=PATH)
    args = parser.parse_args()
    data = json.loads(args.path.read_text(encoding="utf-8"))
    errors = validate(data)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("PSI-1000 valid: 1000 levels / 100 strata / per-project mirror-room self-improvement enforced")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
