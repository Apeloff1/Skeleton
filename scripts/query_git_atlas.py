#!/usr/bin/env python3
"""Budget-limited, Git-SHA-bound source navigation through the canonical atlas.

Only index metadata is returned; no source text is executed, trusted as
instructions, or loaded into LLM context merely because it is indexed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any

# Support `python scripts/query_git_atlas.py` and `python -m scripts.query_git_atlas`.
if __package__:
    from .build_git_atlas import git, SCHEMA
else:
    from build_git_atlas import git, SCHEMA

TERMS = re.compile(r"[a-z][a-z0-9]{1,}")


def _words(text: str) -> set[str]:
    return set(TERMS.findall(text.casefold().replace("_", "/").replace("-", "/")))


def _verified_json(folder: Path, summary: dict[str, Any], filename: str) -> Any:
    record = summary["artifacts"][filename]
    data = (folder / filename).read_bytes()
    if (
        len(data) != record["size"]
        or hashlib.sha256(data).hexdigest() != record["sha256"]
    ):
        raise ValueError(f"index artifact failed integrity verification: {filename}")
    return json.loads(data)


def query(root: Path, atlas: Path, text: str, *, budget_bytes: int = 6000,
          max_hits: int = 12, paths_per_hit: int = 4) -> dict[str, Any]:
    if budget_bytes < 350 or budget_bytes > 250000:
        raise ValueError("context budget must be between 350 and 250000 bytes")
    if not 1 <= max_hits <= 100 or not 0 <= paths_per_hit <= 20:
        raise ValueError("hit/path limits out of bounds")
    terms = _words(text)
    if not terms or len(text) > 2000:
        raise ValueError("query needs bounded meaningful text")
    summary = json.loads((atlas / "summary.json").read_bytes())
    if summary.get("schema") != SCHEMA or summary.get("truncated") is not False:
        raise ValueError("incomplete or incompatible Git atlas")
    sha = git(root.resolve(), "rev-parse", "HEAD").decode().strip()
    if sha != summary["commit"]:
        raise ValueError("stale atlas: checkout SHA does not match index")
    navigation = _verified_json(atlas, summary, "navigation.json")
    if navigation.get("commit") != sha:
        raise ValueError("navigation provenance mismatch")
    candidates: set[str] = set()
    lexicon = navigation["tokens"]
    for term in sorted(terms):
        candidates.update(lexicon.get(term, ()))
        # Prefix expansion is bounded; there is no unbounded fuzzy retrieval.
        for token in sorted(lexicon):
            if token.startswith(term) or (len(term) >= 5 and term.startswith(token)):
                candidates.update(lexicon[token][:500])
    groups = {item["id"]: item for item in navigation["features"]}
    if not candidates:
        candidates = {key for key in groups if any(t in key.casefold() for t in terms)}
    ranked: list[tuple[int, str]] = []
    for feature in candidates:
        record = groups.get(feature)
        if record is None:
            raise ValueError("navigation index contains an orphaned feature")
        words = _words(feature + "/" + record["zone"])
        matches = terms & words
        partial = sum(any(w.startswith(t) for w in words) for t in terms)
        score = 12 * len(matches) + 3 * partial
        if text.casefold() in feature.casefold():
            score += 20
        if score:
            ranked.append((score, feature))
    ranked.sort(key=lambda candidate: (-candidate[0], candidate[1]))
    ranked = ranked[:max_hits]
    selected = {feature: [] for _, feature in ranked}
    if paths_per_hit:
        record = summary["artifacts"]["files.jsonl"]
        path = atlas / "files.jsonl"
        if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("full file ledger digest mismatch")
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                item = json.loads(line)
                fid = item["feature"]
                if fid not in selected:
                    continue
                p = item["path"]
                match = len(terms & _words(p))
                selected[fid].append((match, p, item["blob_sha"]))
    hits: list[dict[str, Any]] = []
    for score, feature in ranked:
        record = groups[feature]
        candidates_for_feature = sorted(
            selected.get(feature, ()), key=lambda item: (-item[0], item[1])
        )[:paths_per_hit]
        hits.append({
            "feature": feature, "zone": record["zone"], "owner": record["owner"],
            "tracked_files": record["files"], "rank": score,
            "files": [{"path": path, "blob_sha": sha} for _, path, sha in candidates_for_feature],
        })
    payload = {
        "schema": "skeleton.git-atlas-context.v1", "commit": sha,
        "query": text, "hits": hits, "truncated_by_budget": False,
        "retrieval": "metadata_only_review_source_before_editing",
    }
    # Keep the emitted JSON below the requested byte budget, always preserving
    # source SHA and provenance. Trimming is deterministic and fail-closed.
    def size() -> int:
        return len(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8"))
    if size() > budget_bytes:
        payload["truncated_by_budget"] = True
    while size() > budget_bytes and any(hit["files"] for hit in hits):
        next_hit = max((h for h in hits if h["files"]), key=lambda h: (len(h["files"]), h["feature"]))
        next_hit["files"].pop()
    while size() > budget_bytes and hits:
        hits.pop()
    if size() > budget_bytes:
        raise ValueError("requested context budget cannot contain the evidence envelope")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--atlas", type=Path, required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--budget-bytes", type=int, default=6000)
    parser.add_argument("--max-hits", type=int, default=12)
    args = parser.parse_args()
    try:
        result = query(args.root, args.atlas, args.query, budget_bytes=args.budget_bytes,
                       max_hits=args.max_hits)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"Git atlas context failed closed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
