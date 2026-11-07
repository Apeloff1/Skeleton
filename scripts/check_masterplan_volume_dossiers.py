#!/usr/bin/env python3
"""Fail-closed, read-only audit of 421 source-bound masterplan volume dossiers.

This is a document-integrity checker, NOT product or release qualification.
All completion authority stays with the canonical machine accountability ledger.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.check_ai_100_large_milestones import run as verify_milestone_sources
DOCS = Path("docs/plan/volume_completion")
SCHEMA = "SOURCE-BOUND-VOLUME-DOSSIER v1"
LAYER_COUNT = 14
MAX_DOC_BYTES = 128 * 1024


def _unique_json(pairs: list[tuple[str, object]]) -> dict:
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate JSON key: " + key)
        out[key] = value
    return out


def _reject_nonfinite(value: str) -> None:
    raise ValueError("non-finite number: " + value)


def _load(root: Path, relative: str) -> tuple[dict, str]:
    raw = (root / relative).read_bytes()
    if len(raw) > 32 * 1024 * 1024:
        raise ValueError("oversized source: " + relative)
    doc = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_unique_json,
        parse_constant=_reject_nonfinite,
    )
    if type(doc) is not dict:
        raise ValueError("JSON object required: " + relative)
    sha = hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()
    return doc, sha


def _ensure(value: bool, problem: str) -> None:
    if not value:
        raise ValueError(problem)


def inspect_dossier(content: str, volume: dict, milestone: dict, source_sha: str) -> None:
    """Validate a single dossier without trusting its own claimed completion."""
    ident = volume["key"]
    marker = (
        f"<!-- {SCHEMA} | {ident} | {milestone['id']} | "
        f"{source_sha} | planning-not-independent-qualification -->"
    )
    _ensure(content.startswith(marker + "\n"), ident + ": source pin / milestone mismatch")
    _ensure(
        "\n# " + ident + " — " + volume["title"] + "\n" in "\n" + content,
        ident + ": incorrect volume title",
    )
    _ensure("**accountability:** " + volume["accountability_id"] in content,
            ident + ": accountability mismatch")
    _ensure("**depth pass:** " + volume["depth_pass"] in content,
            ident + ": depth pass mismatch")
    _ensure("**source status:** " + volume["implementation_status"] in content,
            ident + ": source-state mismatch")
    _ensure("source_blob=" + source_sha in content, ident + ": missing source receipt")
    _ensure("milestone=" + milestone["id"] in content, ident + ": missing milestone receipt")
    _ensure("qualification=UNVERIFIED_BY_THIS_DOSSIER" in content,
            ident + ": missing explicit non-qualification")
    _ensure("qualification=PASSED" not in content,
            ident + ": self-issued qualification is forbidden")
    for field in ("requirements", "capabilities", "contracts",
                  "implementation_paths", "tests", "evaluations", "risks"):
        for original in volume.get(field, []):
            token = "- " + str(original).strip()
            _ensure(token in content, f"{ident}: missing {field} obligation: {token[:90]}")
    actual = re.findall(r"^### L(\d{2}) — ", content, flags=re.MULTILINE)
    _ensure(actual == [f"{n:02d}" for n in range(LAYER_COUNT)],
            ident + ": missing, duplicated or reordered L00-L13 layer")
    _ensure(content.count("## Exit evidence receipt") == 1,
            ident + ": incomplete exit receipt section")


def audit(root: Path = ROOT) -> dict:
    """Check canonical pins, 421 uniquely bound dossiers and the 100-bundle index."""
    root = Path(root)
    # Reuse canonical independent structural validator and its SHA-pin checks.
    source = verify_milestone_sources(root)
    master, master_sha = _load(root, "machine/ai_master_plan.json")
    idx, _ = _load(root, "machine/ai_masterplan_parse_index.json")
    roadmap, _ = _load(root, "machine/ai_100_large_delivery_milestones.json")
    expected_pin = idx["sources"]["machine/ai_master_plan.json"]["git_blob_sha"]
    _ensure(master_sha == expected_pin, "stale canonical source pin")
    vols = master["volumes"]
    _ensure([v["key"] for v in vols] ==
            [f"VOL-{n:03d}" for n in range(421)], "canonical volume inventory drift")
    milestone_by_volume = {}
    for milestone in roadmap["milestones"]:
        for member in milestone["volumes"]:
            key = member["id"]
            _ensure(key not in milestone_by_volume, "duplicate milestone binding " + key)
            milestone_by_volume[key] = milestone
    _ensure(set(milestone_by_volume) == {v["key"] for v in vols},
            "missing / orphaned milestone volume bindings")
    directory = root / DOCS
    found = {path.name for path in directory.glob("VOL-*.md")}
    wanted = {v["key"] + ".md" for v in vols}
    _ensure(found == wanted, "volume dossier file inventory drift: missing=" +
            str(sorted(wanted - found)[:8]) + " extras=" + str(sorted(found - wanted)[:8]))
    for volume in vols:
        path = directory / (volume["key"] + ".md")
        _ensure(not path.is_symlink(), volume["key"] + ": symlink dossier prohibited")
        raw = path.read_bytes()
        _ensure(len(raw) <= MAX_DOC_BYTES, volume["key"] + ": oversized dossier")
        inspect_dossier(raw.decode("utf-8"), volume,
                        milestone_by_volume[volume["key"]], master_sha)
    readme = directory / "README.md"
    _ensure(not readme.is_symlink(), "README symlink prohibited")
    readme_text = readme.read_text(encoding="utf-8")
    _ensure(master_sha in readme_text, "README source pin stale")
    for volume in vols:
        _ensure(f"./{volume['key']}.md" in readme_text,
                "README missing " + volume["key"])
    for milestone in roadmap["milestones"]:
        _ensure(f"| {milestone['id']} |" in readme_text,
                "README missing " + milestone["id"])
    planned = sum(
        item.startswith("planned:")
        for vol in vols for item in vol.get("tests", [])
    )
    return {
        "structural_dossiers_verified": len(vols),
        "milestone_bindings_verified": len(roadmap["milestones"]),
        "mandatory_layers_each": LAYER_COUNT,
        "canonical_source_git_blob": master_sha,
        "source_ledger_signed_volumes": idx["volume_summary"]["complete"],
        "planned_test_references": planned,
        "independent_milestone_qualification_proven_here": 0,
        "canonical_milestone_source_signed_groups": source["all_source_signed_groups"],
        "product_or_release_approval": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.add_argument("--require-independent-qualification", action="store_true")
    args = parser.parse_args()
    try:
        result = audit()
    except (OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        print("FAIL: source-bound volume dossiers: " + str(exc))
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"PASS: {result['structural_dossiers_verified']} source-bound dossiers; "
              f"{result['milestone_bindings_verified']} milestone bindings; "
              "no release qualification granted")
    if args.require_independent_qualification:
        print("FAIL: structural dossiers cannot establish independent qualification")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
