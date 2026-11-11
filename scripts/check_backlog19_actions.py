"""Fail-closed offline validator for the 2026-11-08 nineteen-PR action snapshot.

This immutable observed-head snapshot may predate its own bookkeeping commit;
it documents source/metadata custody and never authorizes a merge,
release, production admission, or substitute for live GitHub exact-head checks.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

LEDGER = Path(__file__).resolve().parents[1] / "machine/backlog19_actions_20261108.json"
SHA = re.compile(r"[0-9a-f]{40}\Z")
CLOSED = {4885: (5062, "closed_superseded"),
          5056: (5041, "closed_duplicate"),
          5055: (5028, "closed_duplicate"),
          5049: (5028, "closed_duplicate"),
          5033: (5028, "closed_duplicate"),
          4902: (5078, "closed_superseded"),
          4990: (5075, "closed_superseded"),
          4889: (5097, "closed_superseded"),
          4836: (5089, "closed_superseded")}
REVIEW = frozenset({5090, 5091, 5038})
QUARANTINE = frozenset({5022, 4991})
STACKED = frozenset({5089, 5081, 4870})
OVERLAP = frozenset({4853, 4838})
EXPECTED = frozenset(CLOSED) | REVIEW | QUARANTINE | STACKED | OVERLAP
ROOT_KEYS = frozenset({"schema", "owner", "record_date", "source", "admission",
                       "total_at_intake", "merges_performed", "releases_performed",
                       "independent_approval_verified", "current_head_ci_complete", "entries"})
ENTRY_KEYS = frozenset({"number", "head_sha", "base", "state", "draft", "merged",
                        "changed_paths", "disposition", "survivor_pr", "source_admitted",
                        "merge_approved", "release_approved", "exact_head_ci_verified"})


class Backlog19Hold(ValueError):
    pass


def require(condition: bool, detail: str) -> None:
    if not condition:
        raise Backlog19Hold(detail)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in obj, "duplicate JSON field")
        obj[key] = value
    return obj


def parse(raw: bytes) -> dict[str, Any]:
    require(type(raw) is bytes and 1 <= len(raw) <= 64 * 1024,
            "unbounded reconciliation record")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              Backlog19Hold("nonfinite JSON constant")))
    except (UnicodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise Backlog19Hold("invalid reconciliation JSON") from exc
    return validate(data)


def validate(data: Any) -> dict[str, Any]:
    require(type(data) is dict and set(data) == ROOT_KEYS, "record schema mismatch")
    require(data["schema"] == "skeleton.backlog19.actions.v1"
            and data["owner"] == "Apeloff1/Skeleton"
            and data["record_date"] == "2026-11-08"
            and data["source"] == "github-observed-heads-before-ledger-commit"
            and data["admission"] == "source_review_only", "untrusted provenance")
    require(type(data["total_at_intake"]) is int and data["total_at_intake"] == 19,
            "intake scope changed")
    require(type(data["merges_performed"]) is int and data["merges_performed"] == 0
            and type(data["releases_performed"]) is int and data["releases_performed"] == 0,
            "merge or release authority fabricated")
    require(data["independent_approval_verified"] is False
            and data["current_head_ci_complete"] is False, "CI or approval fabricated")
    rows = data["entries"]
    require(type(rows) is list and len(rows) == 19, "19 action records required")
    seen: set[int] = set()
    counts: dict[str, int] = {}
    for row in rows:
        require(type(row) is dict and set(row) == ENTRY_KEYS, "bad PR action fields")
        n = row["number"]
        require(type(n) is int and n in EXPECTED and n not in seen,
                "unknown or repeated PR identity")
        seen.add(n)
        require(type(row["head_sha"]) is str and SHA.fullmatch(row["head_sha"]) is not None,
                "invalid immutable head")
        require(type(row["base"]) is str and 1 <= len(row["base"]) <= 160
                and row["base"].strip() == row["base"], "invalid base")
        require(type(row["changed_paths"]) is int
                and 1 <= row["changed_paths"] <= 100000, "bad source inventory")
        require(all(row[k] is False for k in
                    ("merged", "source_admitted", "merge_approved", "release_approved",
                     "exact_head_ci_verified")), "unqualified source admitted")
        if n in CLOSED:
            survivor, kind = CLOSED[n]
            require(row["state"] == "closed" and row["draft"] is True
                    and row["disposition"] == kind and row["survivor_pr"] == survivor,
                    "superseded PR source custody changed")
        elif n in REVIEW:
            require(row["state"] == "open" and row["draft"] is False
                    and row["disposition"] == "review_only"
                    and row["survivor_pr"] is None, "review-only admission modified")
        else:
            kind = ("held_quarantine" if n in QUARANTINE
                    else "held_stacked" if n in STACKED else "held_overlap")
            require(row["state"] == "open" and row["draft"] is True
                    and row["disposition"] == kind and row["survivor_pr"] is None,
                    "held draft promoted or misclassified")
        counts[row["disposition"]] = counts.get(row["disposition"], 0) + 1
    require(seen == EXPECTED, "incomplete nineteen-PR evidence")
    return {"status": "held", "sources": len(seen), "merged": 0, "released": 0,
            "current_head_ci_verified": False, "classes": dict(sorted(counts.items()))}


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=LEDGER)
    args = parser.parse_args()
    try:
        verdict = parse(args.manifest.read_bytes())
    except (OSError, Backlog19Hold) as exc:
        parser.exit(1, "BACKLOG19_HOLD: %s\n" % exc)
    print(json.dumps(verdict, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
