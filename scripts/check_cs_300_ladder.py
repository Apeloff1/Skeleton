#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "machine" / "cs_300_computer_science_ladder.json"
VALID_WPS = {f"W{i:02d}" for i in range(31)}
MATURITY = [
    "planned","specified","implemented","integrated",
    "independently_verified","frontier_hardened","signed_complete",
]

def validate(data: dict) -> list[str]:
    errors: list[str] = []
    scope = data.get("scope", {})
    layers = data.get("layers", [])
    strata = data.get("strata", [])
    waves = data.get("construction_waves", [])

    if data.get("schema_version") != "skeleton.cs_300_frontier_ladder.v1":
        errors.append("unexpected schema_version")
    if scope.get("expands_top_level_volumes") is not False:
        errors.append("CS-300 must not expand top-level volumes")
    if scope.get("frozen_volume_range") != ["VOL-000", "VOL-420"]:
        errors.append("frozen volume range changed")
    if scope.get("relationship_to_frontier_96") != "strictly-above":
        errors.append("CS-300 must remain strictly above Frontier-96")
    if len(layers) != 300:
        errors.append(f"expected 300 layers, got {len(layers)}")
    if len(strata) != 30:
        errors.append(f"expected 30 strata, got {len(strata)}")
    if len(waves) != 30:
        errors.append(f"expected 30 construction waves, got {len(waves)}")

    expected_ids = [f"CS300-{i:03d}" for i in range(1, 301)]
    ids = [layer.get("id") for layer in layers]
    if ids != expected_ids:
        errors.append("layer IDs/order must be exactly CS300-001..CS300-300")

    seen: set[str] = set()
    for i, layer in enumerate(layers, start=1):
        lid = layer.get("id")
        if lid in seen:
            errors.append(f"duplicate layer id: {lid}")
        seen.add(lid)
        if layer.get("ordinal") != i:
            errors.append(f"{lid}: ordinal mismatch")
        expected_stratum = f"CS300-S{((i - 1) // 10) + 1:02d}"
        if layer.get("stratum_id") != expected_stratum:
            errors.append(f"{lid}: expected stratum {expected_stratum}")
        if layer.get("entry_gate") != "frontier-96-qualified":
            errors.append(f"{lid}: missing Frontier-96 entry gate")
        if not layer.get("build_contract") or not layer.get("acceptance_proof"):
            errors.append(f"{lid}: missing build/acceptance contract")
        if layer.get("maturity") not in MATURITY:
            errors.append(f"{lid}: invalid maturity")
        wps = layer.get("owner_work_packages", [])
        if not wps or any(wp not in VALID_WPS for wp in wps):
            errors.append(f"{lid}: invalid or empty owner_work_packages")
        deps = layer.get("depends_on", [])
        for dep in deps:
            if dep not in expected_ids[: i - 1]:
                errors.append(f"{lid}: dependency {dep} is unknown or not earlier")

        complete = layer.get("complete") is True
        if complete:
            if layer.get("maturity") != "signed_complete":
                errors.append(f"{lid}: complete without signed_complete maturity")
            if not layer.get("implementation_signed"):
                errors.append(f"{lid}: complete without implementation signature")
            if not layer.get("independent_verification_signed"):
                errors.append(f"{lid}: complete without independent verification signature")
            if not layer.get("evidence"):
                errors.append(f"{lid}: complete without evidence")

    for idx, st in enumerate(strata, start=1):
        if st.get("id") != f"CS300-S{idx:02d}":
            errors.append(f"stratum {idx}: identity mismatch")
        expected_range = [f"CS300-{((idx-1)*10)+1:03d}", f"CS300-{idx*10:03d}"]
        if st.get("layer_range") != expected_range:
            errors.append(f"{st.get('id')}: layer_range mismatch")

    completion = data.get("completion", {})
    signed_count = sum(1 for layer in layers if layer.get("complete") is True)
    if completion.get("total_layers") != 300:
        errors.append("completion.total_layers must be 300")
    if completion.get("signed_complete") != signed_count:
        errors.append("completion signed_complete does not match layer records")
    should_qualify = signed_count == 300
    if completion.get("cs_300_qualified") is not should_qualify:
        errors.append("cs_300_qualified inconsistent with layer completion")
    if should_qualify and not layers[-1].get("independent_verification_signed"):
        errors.append("CS300-300 lacks independent finality signature")

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
    print("CS-300 ladder valid: 300 layers / 30 strata / 0 top-level volume expansion")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
