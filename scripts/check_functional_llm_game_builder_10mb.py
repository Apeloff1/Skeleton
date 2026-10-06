#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "machine/functional_llm_game_builder_10mb_manifest.json"


def fail(msg: str) -> None:
    raise SystemExit("FLGB masterplan invalid: " + msg)


def main() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("kind") != "functional-llm-game-builder-execution-atlas":
        fail("wrong kind")
    if data.get("plan_version") != "2.5.0":
        fail("unexpected plan version")

    shards = data.get("shards")
    if not isinstance(shards, list) or len(shards) != 18:
        fail("expected 18 shards")
    expected_ids = [f"FLGB-{i:02d}" for i in range(1, 19)]
    if [s.get("id") for s in shards] != expected_ids:
        fail("shard IDs are incomplete or out of order")

    coverage = data.get("coverage", {})
    lifecycle = coverage.get("lifecycle")
    proof_labels = coverage.get("proof_labels")
    stress_scenarios = coverage.get("stress_scenarios")
    if not isinstance(lifecycle, list) or len(lifecycle) != 12:
        fail("expected 12 lifecycle stages")
    if not isinstance(proof_labels, list) or len(proof_labels) != 10:
        fail("expected 10 proof labels")
    if not isinstance(stress_scenarios, list) or len(stress_scenarios) != 12:
        fail("expected 12 stress scenarios")
    policy = coverage.get("coverage_policy", {})
    for key in (
        "subsystem_lifecycle_cartesian_required",
        "evidence_class_presence_per_plane",
        "stress_scenario_presence_per_plane",
    ):
        if policy.get(key) is not True:
            fail(f"coverage policy disabled: {key}")

    total = 0
    for shard in shards:
        shard_id = shard["id"]
        path = ROOT / shard["path"]
        if not path.is_file():
            fail(f"missing {shard['path']}")
        raw = path.read_bytes()
        total += len(raw)
        per_shard_floor = int(data.get("bytes", {}).get("per_shard_minimum", 0))
        if per_shard_floor < 2_300_000:
            fail(f"per-shard minimum regressed: {per_shard_floor}")
        if int(shard.get("min_bytes", 0)) != per_shard_floor:
            fail(f"{shard_id} per-shard minimum drift")
        if len(raw) < per_shard_floor:
            fail(f"undersized {shard['path']}")
        if len(raw) != int(shard["bytes"]):
            fail(f"byte manifest stale for {shard['path']}")
        text = raw.decode("utf-8")

        if f"# {shard_id}" not in text:
            fail(f"header mismatch {shard_id}")
        if "Implementation signed: false" not in text:
            fail(f"missing unsigned implementation marker {shard_id}")
        if "Independent verification signed: false" not in text:
            fail(f"missing unsigned verification marker {shard_id}")
        if "## Coverage Closure Matrix" not in text:
            fail(f"missing coverage closure matrix {shard_id}")

        atom_ids = set(
            re.findall(rf"^## ({re.escape(shard_id)}-\d{{5}})\b", text, re.MULTILINE)
        )
        minimum_atoms = int(shard.get("minimum_requirement_atoms", 450))
        if len(atom_ids) < minimum_atoms:
            fail(f"insufficient requirement atoms in {shard_id}: {len(atom_ids)}")

        heading_matches = re.findall(
            rf"^## {re.escape(shard_id)}-\d{{5}} — (.*?) / (.*?) / (.*?)$",
            text,
            re.MULTILINE,
        )
        if len(heading_matches) != len(atom_ids):
            fail(f"atom heading parse mismatch in {shard_id}")

        required_subsystems = shard.get("subsystems")
        if not isinstance(required_subsystems, list) or len(required_subsystems) != 12:
            fail(f"{shard_id} must register 12 subsystems")
        observed_subsystems = {sub.strip() for sub, _, _ in heading_matches}
        observed_lifecycle = {phase.strip() for _, phase, _ in heading_matches}
        if observed_subsystems != set(required_subsystems):
            fail(f"{shard_id} subsystem heading coverage mismatch")
        if observed_lifecycle != set(lifecycle):
            fail(f"{shard_id} lifecycle heading coverage mismatch")
        observed_pairs = {(sub.strip(), phase.strip()) for sub, phase, _ in heading_matches}
        expected_pairs = {(sub, phase) for sub in required_subsystems for phase in lifecycle}
        missing_pairs = expected_pairs - observed_pairs
        if missing_pairs:
            sample = sorted(missing_pairs)[:5]
            fail(f"{shard_id} missing subsystem/lifecycle pairs: {sample}")

        for index, subsystem in enumerate(required_subsystems, start=1):
            coverage_id = f"COV-{shard_id}-{index:02d}"
            if f"### {coverage_id} — {subsystem}" not in text:
                fail(f"{shard_id} missing coverage record {coverage_id}")
        for proof in proof_labels:
            if proof.lower() not in text.lower():
                fail(f"{shard_id} missing proof dimension {proof}")
        for scenario in stress_scenarios:
            if scenario.lower() not in text.lower():
                fail(f"{shard_id} missing stress dimension {scenario}")
        for token in ("Objective", "Acceptance", "Failure", "provenance", "cancellation"):
            if token.lower() not in text.lower():
                fail(f"{shard_id} missing {token} semantics")

        deep = data.get("deep_closure", {})
        required_deep = int(deep.get("required_atoms_per_plane", 0))
        if required_deep != 1296:
            fail("deep-closure per-plane atom contract drift")
        if shard.get("deep_closure_required") is not True:
            fail(f"{shard_id} deep closure not required")
        if int(shard.get("deep_closure_atoms", 0)) != required_deep:
            fail(f"{shard_id} deep-closure manifest count drift")
        if "## Deep Functional Closure Expansion — Pass 2" not in text:
            fail(f"{shard_id} missing deep-closure pass marker")

        plane_suffix = shard_id.split("-")[-1]
        deep_matches = re.findall(
            rf"^### FLGBX-{re.escape(plane_suffix)}-(\d{{5}}) — (.*?) / (.*?) / (.*?) / (.*?)$",
            text,
            re.MULTILINE,
        )
        if len(deep_matches) != required_deep:
            fail(f"{shard_id} deep-closure atom count mismatch: {len(deep_matches)}")
        deep_ids = [ordinal for ordinal, _, _, _, _ in deep_matches]
        expected_deep_ids = [f"{i:05d}" for i in range(1, required_deep + 1)]
        if deep_ids != expected_deep_ids:
            fail(f"{shard_id} deep-closure ordinals are incomplete or out of order")

        deep_subsystems = {sub.strip() for _, sub, _, _, _ in deep_matches}
        deep_lifecycle = {phase.strip() for _, _, phase, _, _ in deep_matches}
        deep_stress = {stress.strip() for _, _, _, stress, _ in deep_matches}
        deep_proofs = {proof.strip() for _, _, _, _, proof in deep_matches}
        expected_stress = set(deep.get("stress_profiles", []))
        if deep_subsystems != set(required_subsystems):
            fail(f"{shard_id} deep-closure subsystem coverage mismatch")
        if deep_lifecycle != set(lifecycle):
            fail(f"{shard_id} deep-closure lifecycle coverage mismatch")
        if deep_stress != expected_stress:
            fail(f"{shard_id} deep-closure stress coverage mismatch")
        if deep_proofs != set(proof_labels):
            fail(f"{shard_id} deep-closure proof coverage mismatch")

        deep_cartesian = {
            (sub.strip(), phase.strip(), stress.strip())
            for _, sub, phase, stress, _ in deep_matches
        }
        expected_deep_cartesian = {
            (sub, phase, stress)
            for sub in required_subsystems
            for phase in lifecycle
            for stress in expected_stress
        }
        if deep_cartesian != expected_deep_cartesian:
            fail(f"{shard_id} deep-closure cartesian matrix incomplete")

    deep = data.get("deep_closure", {})
    if deep.get("pass_id") != "FLGB-DEEP-CLOSURE-PASS-2":
        fail("missing deep-closure pass identity")
    if int(deep.get("required_atoms_total", 0)) != 23328:
        fail("deep-closure total atom contract drift")
    if deep.get("exact_cartesian_product_required") is not True:
        fail("deep-closure exact cartesian requirement disabled")
    if deep.get("runtime_signoff_forbidden_from_specification_alone") is not True:
        fail("deep-closure runtime signoff protection disabled")

    bytes_cfg = data.get("bytes", {})
    previous_total = int(bytes_cfg.get("previous_shard_total", 0))
    exact_double = previous_total * 2
    if previous_total <= 0:
        fail("missing previous atlas byte baseline")
    if int(bytes_cfg.get("double_baseline_target", 0)) != exact_double:
        fail("literal doubled baseline target drift")
    requested_minimum = int(bytes_cfg.get("requested_minimum", 0))
    if requested_minimum < exact_double:
        fail(f"atlas minimum is below literal doubled baseline: {requested_minimum} < {exact_double}")
    if bytes_cfg.get("doubled_target_met") is not True:
        fail("doubled target marker is not true")
    if total < requested_minimum:
        fail(f"aggregate specification bytes below doubled minimum: {total}")
    if total != int(bytes_cfg["shard_total"]):
        fail("aggregate byte total stale")
    if bytes_cfg.get("human_index_sync_required") is not True:
        fail("human index byte-ledger synchronization disabled")
    if int(bytes_cfg.get("human_index_shard_total", -1)) != total:
        fail("human index byte ledger stale in manifest")
    human_index = ROOT / data["authorities"]["human_index"]
    if not human_index.is_file():
        fail("missing human index")
    human_text = human_index.read_text(encoding="utf-8")
    if f"{total:,}" not in human_text:
        fail("human index byte ledger stale")
    if data["completion"].get("runtime_completion_claim") is not False:
        fail("runtime completion must remain fail-closed")
    if data["completion"].get("implementation_signed") is not False:
        fail("implementation cannot be auto-signed")
    if data["completion"].get("independent_verification_signed") is not False:
        fail("verification cannot be auto-signed")
    if coverage.get("required_planes") != expected_ids:
        fail("coverage planes mismatch")
    if not coverage.get("plan_surface_no_known_unmapped_primary_domain"):
        fail("plan coverage assertion missing")

    e2e = data.get("end_to_end_acceptance", [])
    if not isinstance(e2e, list) or len(e2e) < 12:
        fail("end-to-end spine incomplete")

    shard17 = (ROOT / shards[16]["path"]).read_text(encoding="utf-8")
    for token in ("Forge-100", "Forge-1000", "Forge-10000", "rights", "clean-room"):
        if token.lower() not in shard17.lower():
            fail(f"rival/rights plane missing {token}")

    shard14 = (ROOT / shards[13]["path"]).read_text(encoding="utf-8")
    for token in ("longform", "canon", "continuity", "timeline"):
        if token.lower() not in shard14.lower():
            fail(f"long-form plane missing {token}")

    print(
        f"FLGB masterplan valid: {len(shards)} shards, {total} bytes, "
        "18x12 subsystem/lifecycle coverage matrices plus 23,328 deep-closure atoms present, "
        "runtime completion remains unsigned"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
