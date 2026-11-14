"""Versioned native candidate admission matrix manifest."""
from __future__ import annotations
from importlib import resources
from .strict import decode
from .errors import deny

DOMAINS = ("canonical", "identity", "rights", "dedup", "split", "plan",
           "state", "roles", "privacy", "source_truth", "resource", "digest")
PER_DOMAIN = 24


def read_cases():
    root = resources.files(__package__) / "vectors"
    seen = set()
    for domain in DOMAINS:
        count = 0
        for path in sorted((root / domain).iterdir(), key=lambda item: item.name):
            if path.suffix != ".json" or not path.name.startswith(domain + "_"):
                deny("vector-extension")
            row = decode(path.read_bytes())
            if (type(row) is not dict or row.get("schema") != "skeleton.native-candidate.vector.v1"
                    or row.get("domain") != domain or row.get("id") != path.stem
                    or row.get("id") in seen or type(row.get("expected_allow")) is not bool
                    or type(row.get("input")) is not dict or row.get("model_qualified") is not False):
                deny("vector-identity")
            seen.add(row["id"])
            count += 1
            yield row
        if count != PER_DOMAIN:
            deny("vector-incomplete")



def run_all() -> dict:
    from .vector_evaluator import evaluate
    records = []
    for case in read_cases():
        outcome = evaluate(case["domain"], case["input"])
        records.append({
            "id": case["id"], "expected_allow": case["expected_allow"],
            "actual_allow": outcome["allowed"],
            "code": outcome["code"],
            "passed": case["expected_allow"] is outcome["allowed"],
        })
    failures = [x["id"] for x in records if not x["passed"]]
    return {
        "schema": "skeleton.native-candidate.vector-report.v1",
        "total": len(records), "passed": len(records)-len(failures),
        "failed": len(failures), "failure_ids": failures,
        "real_model_trained": False,
        "model_qualified": False,
        "release_certified": False,
    }
