#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "machine" / "learning_400_adversarial_400.json"
MATURITY = [
    "planned","specified","implemented","integrated",
    "independently_verified","adversarially_qualified","signed_complete",
]
RANK = {state: i for i, state in enumerate(MATURITY)}
VALID_WPS = {f"W{i:02d}" for i in range(31)}

def validate(data: dict) -> list[str]:
    errors: list[str] = []
    ll = data.get("learning_layers", [])
    al = data.get("adversarial_layers", [])
    ls = data.get("learning_strata", [])
    ads = data.get("adversarial_strata", [])
    waves = data.get("construction_waves", [])
    scope = data.get("scope", {})

    if data.get("schema_version") != "skeleton.learning_400_adversarial_400.v1":
        errors.append("unexpected schema_version")
    if len(ll) != 400 or len(al) != 400:
        errors.append(f"expected 400+400 layers, got {len(ll)}+{len(al)}")
    if len(ls) != 40 or len(ads) != 40:
        errors.append(f"expected 40+40 strata, got {len(ls)}+{len(ads)}")
    if len(waves) != 40:
        errors.append(f"expected 40 paired waves, got {len(waves)}")
    if scope.get("expands_top_level_volumes") is not False:
        errors.append("learning overlays must not expand top-level volumes")
    if scope.get("frozen_volume_range") != ["VOL-000", "VOL-420"]:
        errors.append("frozen volume range changed")

    expected_l = [f"L400-{i:03d}" for i in range(1, 401)]
    expected_a = [f"A400-{i:03d}" for i in range(1, 401)]
    if [x.get("id") for x in ll] != expected_l:
        errors.append("learning IDs/order must be exactly L400-001..L400-400")
    if [x.get("id") for x in al] != expected_a:
        errors.append("adversarial IDs/order must be exactly A400-001..A400-400")

    amap = {x.get("id"): x for x in al}
    lmap = {x.get("id"): x for x in ll}

    for i, layer in enumerate(ll, start=1):
        lid = layer.get("id")
        aid = f"A400-{i:03d}"
        if layer.get("ordinal") != i:
            errors.append(f"{lid}: ordinal mismatch")
        if layer.get("stratum_id") != f"L400-S{((i-1)//10)+1:02d}":
            errors.append(f"{lid}: stratum mismatch")
        if layer.get("paired_adversarial_layer") != aid:
            errors.append(f"{lid}: paired adversarial mismatch")
        if layer.get("entry_gate") != "frontier-96-qualified":
            errors.append(f"{lid}: wrong entry gate")
        if layer.get("maturity") not in RANK:
            errors.append(f"{lid}: invalid maturity")
        if not layer.get("build_contract") or not layer.get("acceptance_proof"):
            errors.append(f"{lid}: missing build/proof contract")
        wps = layer.get("owner_work_packages", [])
        if not wps or any(wp not in VALID_WPS for wp in wps):
            errors.append(f"{lid}: invalid work packages")
        for dep in layer.get("depends_on", []):
            if dep not in expected_l[:i-1]:
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
            if not amap.get(aid, {}).get("complete"):
                errors.append(f"{lid}: complete while paired {aid} is incomplete")

    for i, layer in enumerate(al, start=1):
        aid = layer.get("id")
        lid = f"L400-{i:03d}"
        if layer.get("ordinal") != i:
            errors.append(f"{aid}: ordinal mismatch")
        if layer.get("stratum_id") != f"A400-S{((i-1)//10)+1:02d}":
            errors.append(f"{aid}: stratum mismatch")
        if layer.get("paired_learning_layer") != lid:
            errors.append(f"{aid}: paired learning mismatch")
        if layer.get("entry_gate") != "paired-learning-specified":
            errors.append(f"{aid}: wrong entry gate")
        if layer.get("maturity") not in RANK:
            errors.append(f"{aid}: invalid maturity")
        if not layer.get("challenge_contract") or not layer.get("acceptance_proof"):
            errors.append(f"{aid}: missing challenge/proof contract")
        wps = layer.get("owner_work_packages", [])
        if not wps or "W19" not in wps or any(wp not in VALID_WPS for wp in wps):
            errors.append(f"{aid}: invalid adversarial work packages")
        for dep in layer.get("depends_on", []):
            if dep not in expected_a[:i-1]:
                errors.append(f"{aid}: dependency {dep} is unknown or not earlier")
        if layer.get("complete") is True:
            if layer.get("maturity") != "signed_complete":
                errors.append(f"{aid}: complete without signed_complete maturity")
            if not layer.get("implementation_signed"):
                errors.append(f"{aid}: complete without implementation signature")
            if not layer.get("independent_verification_signed"):
                errors.append(f"{aid}: complete without independent verification signature")
            if not layer.get("evidence"):
                errors.append(f"{aid}: complete without evidence")
            paired = lmap.get(lid, {})
            if RANK.get(paired.get("maturity"), -1) < RANK["integrated"]:
                errors.append(f"{aid}: complete before paired {lid} is integrated")

    policy = data.get("acquisition_policy", {})
    required_true = [
        "public_web","authorized_sources","robots_and_terms_governed",
        "feeds_and_apis","rendered_dynamic_content","video_audio_understanding",
        "source_provenance_required","rights_privacy_retention_required",
    ]
    for key in required_true:
        if policy.get(key) is not True:
            errors.append(f"acquisition policy {key} must be true")
    for key in ["authentication_bypass","paywall_bypass","anti_bot_evasion"]:
        if policy.get(key) is not False:
            errors.append(f"acquisition policy {key} must be false")

    weights = data.get("weight_policy", {})
    for key in [
        "native_weight_creation","native_pretraining","project_specific_adapters",
        "continual_candidate_learning","weight_editing_and_merging",
    ]:
        if weights.get(key) is not True:
            errors.append(f"weight policy {key} must be true")
    if weights.get("production_in_place_self_mutation") is not False:
        errors.append("production weights must not silently self-mutate in place")

    completion = data.get("completion", {})
    ldone = sum(x.get("complete") is True for x in ll)
    adone = sum(x.get("complete") is True for x in al)
    if completion.get("learning_signed_complete") != ldone:
        errors.append("learning completion count mismatch")
    if completion.get("adversarial_signed_complete") != adone:
        errors.append("adversarial completion count mismatch")
    if completion.get("learning_400_qualified") is not (ldone == 400):
        errors.append("learning_400_qualified mismatch")
    if completion.get("adversarial_400_qualified") is not (adone == 400):
        errors.append("adversarial_400_qualified mismatch")
    if completion.get("paired_system_qualified") is not (ldone == 400 and adone == 400):
        errors.append("paired_system_qualified mismatch")
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
    print("Learning-400 + Adversarial-400 valid: 400 + 400 layers / 80 strata / paired qualification enforced")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
