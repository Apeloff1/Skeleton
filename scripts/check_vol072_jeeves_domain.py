#!/usr/bin/env python3
"""Independent repository verifier for VOL-072 Jeeves Domain System."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
CUSTODY = ROOT / "machine/jeeves_custody.json"
TREE = ROOT / "machine/ai_file_tree.json"
CANONICAL = ROOT / "skeleton/jeeves/evidence_response.py"
MIRROR = ROOT / "skeleton/ai/agents/jeeves/evidence_response.py"

EXPECTED = {
    "AIFT-JEEVES": ("canonical_authority", True, "cutover:parity-ready"),
    "AIFT-V2-BACKEND-CORE-JEEVES-CAPABILITIES": ("compatibility_only", False, "cutover:merge-required"),
    "AIFT-V2-BACKEND-CORE-JEEVES-CONTROL-PLANE": ("compatibility_only", False, "cutover:merge-required"),
    "AIFT-V2-BACKEND-CORE-JEEVES-EXECUTION-KERNEL": ("compatibility_only", False, "cutover:merge-required"),
    "AIFT-V2-BACKEND-CORE-JEEVES-MEMORY": ("compatibility_only", False, "cutover:merge-required"),
    "AIFT-V2-BACKEND-CORE-KNOWLEDGE-AUGMENTED-JEEVES": ("compatibility_only", False, "cutover:merge-required"),
    "AIFT-V2B-GAMEFORGE-JEEVES": ("research_quarantine", False, "cutover:quarantine"),
}


def validate() -> list[str]:
    errors: list[str] = []
    custody = json.loads(CUSTODY.read_text(encoding="utf-8"))
    tree = json.loads(TREE.read_text(encoding="utf-8"))
    if custody.get("schema_version") != 1:
        errors.append("custody schema_version must be 1")
    if custody.get("volume") != "VOL-072":
        errors.append("custody manifest must bind VOL-072")
    if custody.get("policy", {}).get("no_parallel_authority") is not True:
        errors.append("Jeeves custody must prohibit parallel authority")

    entries = custody.get("entries")
    if not isinstance(entries, list):
        return errors + ["custody entries must be a list"]
    by_id = {
        item.get("mapping_id"): item
        for item in entries
        if isinstance(item, dict) and isinstance(item.get("mapping_id"), str)
    }
    if set(by_id) != set(EXPECTED):
        errors.append("custody manifest must exactly cover required Jeeves mappings")

    tree_by_id = {
        item.get("id"): item
        for item in tree.get("mappings", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    authority_count = 0
    for mapping_id, (custody_class, authority, cutover_tag) in EXPECTED.items():
        entry = by_id.get(mapping_id)
        mapping = tree_by_id.get(mapping_id)
        if entry is None or mapping is None:
            errors.append(f"missing governed Jeeves mapping {mapping_id}")
            continue
        if entry.get("custody") != custody_class:
            errors.append(f"{mapping_id} custody class drift")
        if entry.get("runtime_authority") is not authority:
            errors.append(f"{mapping_id} authority drift")
        authority_count += int(entry.get("runtime_authority") is True)
        if entry.get("source") != mapping.get("source"):
            errors.append(f"{mapping_id} source drift")
        if entry.get("destination") != mapping.get("destination"):
            errors.append(f"{mapping_id} destination drift")
        if cutover_tag not in mapping.get("move_tags", []):
            errors.append(f"{mapping_id} missing required cutover tag")
        if entry.get("required_cutover_tag") != cutover_tag:
            errors.append(f"{mapping_id} custody/tag disagreement")

    if authority_count != 1:
        errors.append("exactly one Jeeves runtime authority is required")
    if not CANONICAL.is_file() or not MIRROR.is_file():
        errors.append("Jeeves evidence implementation/mirror missing")
    elif CANONICAL.read_bytes() != MIRROR.read_bytes():
        errors.append("canonical and governed Jeeves evidence authority must be byte-identical")

    if not errors:
        spec = importlib.util.spec_from_file_location("vol072_evidence_response", CANONICAL)
        if not spec or not spec.loader:
            errors.append("unable to import canonical Jeeves evidence authority")
        else:
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            required = {
                "JeevesEvidenceAuthority",
                "JeevesEvidenceError",
                "JeevesEvidenceKind",
                "JeevesEvidenceRecord",
                "JeevesEvidenceResponse",
                "JeevesFreshnessPolicy",
            }
            missing = sorted(required - set(module.__all__))
            if missing:
                errors.append(f"canonical Jeeves export contract missing: {missing}")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"VOL-072 ERROR: {error}")
        return 1
    print("VOL-072 OK: singular custody, compatibility/quarantine classification, canonical/AI parity, and evidence-response contract verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
