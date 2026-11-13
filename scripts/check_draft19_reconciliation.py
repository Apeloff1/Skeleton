"""Validate the 19-source reconciliation ledger offline without implying CI success."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

LEDGER = Path(__file__).resolve().parents[1] / "machine" / "draft19_reconciliation.json"
NUMBERS = frozenset((5069, 5062, 5056, 5055, 5049, 5038, 5033, 5028, 5022, 4994, 4991, 4990, 4902, 4889, 4885, 4870, 4853, 4838, 4836))
REQUIRED = frozenset(("Merge Readiness", "Backend Quality", "App Foundation E2E", "Malware Gate", "Artifact Policy", "Repository Hygiene Gate", "Secret scanning", "Dependency Review", "Workflow Input Security", "Sealed Context Guard"))
KIND = frozenset(("overlap", "unwired", "quarantine", "historical"))
SHA = re.compile("[0-9a-f]{40}\\Z")


class AdmissionError(ValueError):
    pass


def must(ok: bool, reason: str) -> None:
    if not ok:
        raise AdmissionError(reason)


def validate(data: Any) -> dict[str, Any]:
    must(type(data) is dict and set(data) == {"schema", "owner", "baseline_pr", "baseline_head", "admission", "merge_approved", "release_approved", "required_gates", "source_prs"}, "schema mismatch")
    must(data["schema"] == "draft19-reconciliation/v1" and data["owner"] == "Apeloff1/Skeleton", "provenance mismatch")
    must(type(data["baseline_pr"]) is int and data["baseline_pr"] == 5074, "unapproved baseline")
    must(type(data["baseline_head"]) is str and SHA.fullmatch(data["baseline_head"]) is not None, "invalid SHA")
    must(data["admission"] == "review_only", "unsafe admission")
    must(data["merge_approved"] is False and data["release_approved"] is False, "security hold removed")
    gates = data["required_gates"]
    must(type(gates) is list and len(gates) == len(REQUIRED) and all(type(x) is str for x in gates) and set(gates) == REQUIRED, "mandatory exact-head gates absent")
    sources = data["source_prs"]
    must(type(sources) is list and len(sources) == 19, "19 originals required")
    seen: set[int] = set()
    counts: dict[str, int] = {}
    for source in sources:
        must(type(source) is dict and set(source) == {"number", "head_sha", "classification", "changed_paths", "source_admitted", "merge_approved", "release_approved"}, "bad source fields")
        n = source["number"]
        must(type(n) is int and n in NUMBERS and n not in seen, "unauthorized or duplicate PR")
        seen.add(n)
        must(type(source["head_sha"]) is str and SHA.fullmatch(source["head_sha"]) is not None, "invalid source head")
        must(type(source["changed_paths"]) is int and 0 < source["changed_paths"] <= 100000, "invalid file count")
        kind = source["classification"]
        must(type(kind) is str and kind in KIND, "unknown disposition")
        must(all(source[k] is False for k in ("source_admitted", "merge_approved", "release_approved")), "held source admitted")
        if n == 5022:
            must(kind == "quarantine", "quarantine removed")
        if n == 5038:
            must(kind == "unwired", "unwired model code promoted")
        if n == 4991:
            must(kind == "historical", "historical source promoted")
        counts[kind] = counts.get(kind, 0) + 1
    must(seen == NUMBERS, "incomplete source inventory")
    return {"status": "review_only", "sources": len(seen), "admitted": 0,
            "remote_ci_verified": False, "classes": dict(sorted(counts.items()))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=LEDGER)
    args = parser.parse_args()
    try:
        result = validate(json.loads(args.manifest.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, AdmissionError) as exc:
        parser.exit(1, "RECONCILIATION_HOLD: %s\n" % exc)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
