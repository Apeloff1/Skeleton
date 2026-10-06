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
        if len(raw) < int(shard.get("min_bytes", 620000)):
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

    if total < 10_000_000:
        fail(f"aggregate specification bytes below 10MB: {total}")
    if total != int(data["bytes"]["shard_total"]):
        fail("aggregate byte total stale")
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
        "18x12 subsystem/lifecycle coverage matrices present, "
        "runtime completion remains unsigned"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
