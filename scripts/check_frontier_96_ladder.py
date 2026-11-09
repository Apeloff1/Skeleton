#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "machine" / "frontier_96_ai_ladder.json"

VALID_WPS = {f"W{i:02d}" for i in range(31)}
MATURITY = [
    "planned",
    "specified",
    "implemented",
    "integrated",
    "independently_verified",
    "frontier_hardened",
    "signed_complete",
]

def validate(data: dict) -> list[str]:
    errors: list[str] = []
    scope = data.get("scope", {})
    layers = data.get("layers", [])
    strata = data.get("strata", [])

    if data.get("schema_version") != "skeleton.frontier_96_ai_ladder.v1":
        errors.append("unexpected schema_version")
    if scope.get("expands_top_level_volumes") is not False:
        errors.append("Frontier-96 must not expand top-level volumes")
    if scope.get("frozen_volume_range") != ["VOL-000", "VOL-420"]:
        errors.append("frozen volume range changed")
    if len(layers) != 96:
        errors.append(f"expected 96 layers, got {len(layers)}")
    if len(strata) != 12:
        errors.append(f"expected 12 strata, got {len(strata)}")

    expected_ids = [f"F96-{i:03d}" for i in range(1, 97)]
    ids = [layer.get("id") for layer in layers]
    if ids != expected_ids:
        errors.append("layer IDs/order must be exactly F96-001..F96-096")

    seen: set[str] = set()
    for i, layer in enumerate(layers, start=1):
        lid = layer.get("id")
        if lid in seen:
            errors.append(f"duplicate layer id: {lid}")
        seen.add(lid)

        if layer.get("ordinal") != i:
            errors.append(f"{lid}: ordinal mismatch")
        expected_stratum = f"F96-S{((i - 1) // 8) + 1:02d}"
        if layer.get("stratum_id") != expected_stratum:
            errors.append(f"{lid}: expected stratum {expected_stratum}")
        if layer.get("entry_gate") != "enterprise-superiority-qualified":
            errors.append(f"{lid}: missing enterprise-superiority entry gate")
        if layer.get("maturity") not in MATURITY:
            errors.append(f"{lid}: invalid maturity")
        wps = layer.get("owner_work_packages", [])
        if not wps or any(wp not in VALID_WPS for wp in wps):
            errors.append(f"{lid}: invalid or empty owner_work_packages")
        deps = layer.get("depends_on", [])
        for dep in deps:
            if dep not in expected_ids[: i - 1]:
                errors.append(f"{lid}: dependency {dep} is unknown or not earlier in the ladder")

        signed = layer.get("maturity") == "signed_complete" or layer.get("complete") is True
        if signed:
            if not layer.get("implementation_signed"):
                errors.append(f"{lid}: complete without implementation signature")
            if not layer.get("independent_verification_signed"):
                errors.append(f"{lid}: complete without independent verification signature")
            if not layer.get("evidence"):
                errors.append(f"{lid}: complete without evidence")

    completion = data.get("completion", {})
    signed_count = sum(1 for layer in layers if layer.get("complete") is True)
    if completion.get("total_layers") != 96:
        errors.append("completion.total_layers must be 96")
    if completion.get("signed_complete") != signed_count:
        errors.append("completion signed_complete does not match layer records")
    should_qualify = signed_count == 96
    if completion.get("frontier_96_qualified") is not should_qualify:
        errors.append("frontier_96_qualified inconsistent with layer completion")

    if data.get("terminology", {}).get("public_architecture_claim") is not False:
        errors.append("must not claim current ChatGPT has a public fixed 96-layer architecture")

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
    print("Frontier-96 ladder valid: 96 layers / 12 strata / no top-level volume expansion")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
