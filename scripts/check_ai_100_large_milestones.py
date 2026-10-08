#!/usr/bin/env python3
"""Fail-closed verification for the 100 large Skeleton AI delivery milestones."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "master_plan": "machine/ai_master_plan.json",
    "advanced_ladder": "machine/advanced_ai_structure_100.json",
    "accountability_index": "machine/ai_masterplan_parse_index.json",
    "accountability": "machine/ai_build_accountability.json",
}


def git_blob_sha(data: bytes) -> str:
    header = ("blob " + str(len(data))).encode("ascii") + bytes([0])
    return hashlib.sha1(header + data).hexdigest()


def load_json(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    if len(raw) > 32 * 1024 * 1024:
        raise ValueError("oversized source: " + str(path))
    def unique(pairs):
        result = {}
        for key, val in pairs:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = val
        return result
    def nonfinite(value):
        raise ValueError("invalid number: " + value)
    parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=nonfinite)
    if type(parsed) is not dict:
        raise ValueError("object root required: " + str(path))
    return parsed, git_blob_sha(raw)


def verify(roadmap: dict, master: dict, ladder: dict, index: dict, shas: dict) -> None:
    def check(ok: bool, message: str) -> None:
        if not ok:
            raise ValueError(message)

    check(roadmap.get("schema_version") == "skeleton.ai.100_large_delivery_milestones.v1", "bad schema")
    check(roadmap.get("status") == "execution_overlay_unqualified", "false completion")
    check(master.get("breadth_freeze", {}).get("enabled") is True, "breadth unfrozen")
    check(master["breadth_freeze"].get("last_top_level_volume") == 420, "breadth drift")
    pins = roadmap.get("source_pins", {})
    check(set(pins) == set(FILES), "source inventory drift")
    for key, path in FILES.items():
        check(pins.get(key) == {"path": path, "git_blob_sha": shas[key]}, "stale source " + key)
    for key in ("master_plan", "accountability"):
        check(index.get("sources", {}).get(FILES[key], {}).get("git_blob_sha") == shas[key], "stale navigation " + key)
    volumes = master.get("volumes", [])
    levels = ladder.get("levels", [])
    milestones = roadmap.get("milestones", [])
    trains = roadmap.get("delivery_trains", [])
    check(len(volumes) == 421 and len(levels) == 100, "source plan size drift")
    check(len(milestones) == 100 and len(trains) == 10, "100 milestone / ten train contract broken")
    keys = [f"VOL-{i:03d}" for i in range(421)]
    check([v["key"] for v in volumes] == keys, "volume identity drift")
    check([x["id"] for x in levels] == [f"L{i:03d}" for i in range(1, 101)], "ladder drift")
    bands = ladder["maturity_bands"]
    check(len(bands) == 10, "band drift")
    for i, train in enumerate(trains):
        check(train["id"] == f"MDT-{i+1:02d}", "train ID drift")
        check(train["name"] == f"Delivery train {i+1} — {bands[i]['name']}", "train title drift")
    used = []
    offset = 0
    gates = {
        "all_volume_implementation_evidence_current",
        "all_volume_independent_verification_current",
        "no_unresolved_noncompensable_security_or_recovery_failure",
        "source_exact_head_requalification",
        "verified_rollback_or_safe_disable_path",
    }
    for i, milestone in enumerate(milestones):
        name = f"MDM-{i+1:03d}"
        amount = 5 if i < 21 else 4
        original = volumes[offset:offset+amount]
        check(milestone["id"] == name and type(milestone["ordinal"]) is int
              and milestone["ordinal"] == i+1, name+" identity drift")
        check(milestone["delivery_train"] == f"MDT-{i//10+1:02d}", name+" train drift")
        check(milestone["advanced_level_context"] == levels[i]["id"], name+" ladder mismatch")
        check(milestone["status"] == "unverified" and milestone["completion_signoff"] is None,
              name+" unearned completion")
        check(len(milestone["exit_gates"]) == len(gates) and set(milestone["exit_gates"]) == gates,
              name+" missing noncompensable gate")
        check(milestone["title"] == f"{original[0]['title']} → {original[-1]['title']}", name+" title drift")
        check(milestone["scope"] ==
              f"Deliver and independently qualify {amount} canonical masterplan volumes: " +
              "; ".join(v["title"] for v in original) + ".", name+" scope drift")
        bindings = milestone["volumes"]
        check(len(bindings) == amount, name+" not a major volume bundle")
        for item, vol in zip(bindings, original):
            expected = {
                "id": vol["key"], "title": vol["title"],
                "accountability": vol["accountability_id"],
                "contract_targets": vol["implementation_paths"][:2],
                "acceptance_tests": vol["tests"][:2],
                "required_outcome": vol["requirements"][:2],
            }
            check(item == expected and bool(item["acceptance_tests"]), name+" fabricated/missing obligations")
            used.append(item["id"])
        d = milestone.get("deliverable_contract", {})
        check(set(d) == {"implementation", "validation", "operational", "proof"}
              and all(type(s) is str and len(s) >= 40 for s in d.values()),
              name+" inadequate deliverables")
        offset += amount
    check(used == keys and offset == 421, "incomplete or duplicated 421-volume coverage")
    check(roadmap["qualification"]["evidence_source"] == FILES["accountability"],
          "noncanonical completion authority")
    check(roadmap["qualification"]["indexed_navigation"] == FILES["accountability_index"],
          "noncanonical navigation source")


def report(roadmap: dict, index: dict) -> dict:
    """Compute actionable source-evidence gaps, never qualification receipts."""
    signed = index.get("fast_sets", {}).get("fully_complete", [])
    waiting = index.get("fast_sets", {}).get("gap_free_waiting_verification", [])
    unsigned = index.get("fast_sets", {}).get("implementation_unsigned", [])
    legal = {f"VOL-{i:03d}" for i in range(421)}
    for label, values in (
        ("signed", signed), ("waiting", waiting), ("unsigned", unsigned),
    ):
        if (type(values) is not list or len(set(values)) != len(values)
                or not set(values) <= legal):
            raise ValueError("invalid source " + label + " volume set")
    if set(signed) & (set(waiting) | set(unsigned)):
        raise ValueError("contradictory source evidence sets")
    statuses = []
    for m in roadmap["milestones"]:
        incomplete = [v for v in m["volumes"] if v["id"] not in signed]
        next_actions = []
        for volume in incomplete:
            ref = volume["id"]
            if ref in unsigned:
                action = "implementation_and_independent_verification"
            elif ref in waiting:
                action = "independent_verification_with_fresh_exact_head_tests"
            else:
                action = "reconcile_current_implementation_and_independent_evidence"
            next_actions.append({
                "volume": ref,
                "action": action,
                "tests": volume["acceptance_tests"],
                "implementation_paths": volume["contract_targets"],
            })
        statuses.append({
            "id": m["id"], "title": m["title"],
            "train": m["delivery_train"],
            "signed_source_volumes": len(m["volumes"]) - len(incomplete),
            "total_volumes": len(m["volumes"]),
            "remaining": next_actions,
        })
    # Evidence proximity is a discovery aid, never a severity override of
    # active ESS-1000 or security incidents.
    near = sorted(statuses, key=lambda x: (
        -x["signed_source_volumes"], len(x["remaining"]), x["id"],
    ))
    return {
        "milestones_defined": 100,
        "volumes_covered": 421,
        "source_signed_volumes": len(signed),
        "all_source_signed_groups": sum(
            x["signed_source_volumes"] == x["total_volumes"] for x in statuses
        ),
        "independently_qualified_milestones": 0,
        "evidence_proximity_shortlist": [row["id"] for row in near[:10]],
        "milestones": statuses,
    }


def run(root: Path = ROOT) -> dict:
    roadmap, _ = load_json(root / "machine/ai_100_large_delivery_milestones.json")
    docs = {}
    shas = {}
    for key, path in FILES.items():
        docs[key], shas[key] = load_json(root / path)
    verify(roadmap, docs["master_plan"], docs["advanced_ladder"],
           docs["accountability_index"], shas)
    return report(roadmap, docs["accountability_index"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    try:
        state = run()
    except (OSError, TypeError, ValueError, KeyError) as exc:
        print("FAIL: 100 large milestone evidence: " + str(exc))
        return 1
    if args.json:
        print(json.dumps(state, indent=2))
    else:
        print(f"PASS: 100 large milestones / 421 volumes; "
              f"{state['all_source_signed_groups']} source-signed groups; "
              f"0 independently qualified.")
    if args.require_complete:
        print("FAIL: 100/100 independent milestone qualifications not established")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
