#!/usr/bin/env python3
"""Deterministic structural test-evidence ranking for repository intelligence.

This layer never claims coverage or test sufficiency. It ranks likely focused tests
from repository graph evidence so agents can spend machine time on the most relevant
checks first, while integration/release gates remain authoritative.
"""
from __future__ import annotations

from collections import defaultdict, deque
import json
from pathlib import Path
import sys
from typing import Any

import repo_intel as base

ROOT = base.ROOT
MAX_TRANSITIVE_DEPTH = 3


def _is_test(row: dict[str, Any]) -> bool:
    return bool((row.get("flags") or {}).get("test"))


def _file_edges(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        edge
        for edge in snapshot.get("graph", {}).get("edges", [])
        if str(edge.get("from", "")).startswith("file:")
        and str(edge.get("to", "")).startswith("file:")
    ]


def build(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build source -> ranked test evidence from direct and bounded transitive links."""
    rows = {str(row["path"]): row for row in snapshot.get("files", [])}
    tests = {path for path, row in rows.items() if _is_test(row)}
    sources = {
        path
        for path, row in rows.items()
        if not _is_test(row)
        and str(row.get("role", "")) in {"python-source", "js-source"}
    }

    imports: dict[str, list[tuple[str, str]]] = defaultdict(list)
    explicit_tests: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for edge in _file_edges(snapshot):
        source = str(edge["from"])[5:]
        target = str(edge["to"])[5:]
        precision = str(edge.get("precision", "unknown"))
        if edge.get("type") == "imports":
            imports[source].append((target, precision))
        elif edge.get("type") == "tests" and source in tests:
            explicit_tests[target].append((source, precision))

    evidence: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)

    def add(source: str, test: str, confidence: float, reason: str, precision: str, depth: int) -> None:
        if source not in sources or test not in tests:
            return
        candidate = {
            "test": test,
            "confidence": round(max(0.0, min(confidence, 1.0)), 3),
            "reason": reason,
            "precision": precision,
            "depth": depth,
        }
        current = evidence[source].get(test)
        if current is None or float(candidate["confidence"]) > float(current["confidence"]):
            evidence[source][test] = candidate

    for source, linked_tests in explicit_tests.items():
        for test, precision in linked_tests:
            add(source, test, 0.9, "explicit-test-edge", precision, 1)

    for test in sorted(tests):
        for target, precision in imports.get(test, []):
            if target in sources:
                confidence = 0.98 if precision == "ast" else 0.82
                add(target, test, confidence, "direct-test-import", precision, 1)

        # Bounded traversal lets a test importing an adapter/module imply lower
        # confidence evidence for deeper local dependencies without pretending
        # it is equivalent to direct coverage.
        queue = deque((target, 1, precision) for target, precision in imports.get(test, []))
        seen = {test}
        while queue:
            current, depth, precision = queue.popleft()
            if current in seen or depth > MAX_TRANSITIVE_DEPTH:
                continue
            seen.add(current)
            if current in sources and depth > 1:
                confidence = 0.72 * (0.72 ** (depth - 2))
                add(current, test, confidence, "transitive-test-import", precision, depth)
            if depth < MAX_TRANSITIVE_DEPTH:
                for nxt, nxt_precision in imports.get(current, []):
                    queue.append((nxt, depth + 1, nxt_precision))

    by_source = {
        source: sorted(
            candidates.values(),
            key=lambda item: (-float(item["confidence"]), item["test"], item["reason"]),
        )
        for source, candidates in sorted(evidence.items())
    }
    covered_sources = sum(1 for source in sources if by_source.get(source))
    link_count = sum(len(items) for items in by_source.values())
    return {
        "schema": 1,
        "max_transitive_depth": MAX_TRANSITIVE_DEPTH,
        "source_count": len(sources),
        "test_file_count": len(tests),
        "sources_with_test_evidence": covered_sources,
        "source_evidence_ratio": covered_sources / max(1, len(sources)),
        "evidence_link_count": link_count,
        "by_source": by_source,
        "semantics": (
            "Confidence ranks structural relevance only. It is not statement/branch coverage, historical pass probability, "
            "or proof that selected tests are sufficient. Full authoritative gates still apply."
        ),
    }


def select_for_impact(
    impact: dict[str, Any], test_evidence: dict[str, Any], limit: int = 100
) -> list[dict[str, Any]]:
    """Aggregate ranked tests across the affected file set."""
    ranked: dict[str, dict[str, Any]] = {}
    by_source = test_evidence.get("by_source", {})
    for source in impact.get("affected_files", []):
        for item in by_source.get(source, []):
            test = str(item["test"])
            score = float(item["confidence"])
            current = ranked.setdefault(
                test,
                {
                    "test": test,
                    "confidence": score,
                    "reasons": [],
                    "sources": [],
                },
            )
            current["confidence"] = max(float(current["confidence"]), score)
            reason = f"{source}:{item['reason']}:{item['precision']}:d{item['depth']}"
            if reason not in current["reasons"]:
                current["reasons"].append(reason)
            if source not in current["sources"]:
                current["sources"].append(source)

    # Preserve tests already surfaced by reverse-impact traversal as strong
    # candidates even if the source/test relation is not semantically indexed.
    for test in impact.get("candidate_tests", []):
        current = ranked.setdefault(
            str(test),
            {
                "test": str(test),
                "confidence": 0.75,
                "reasons": [],
                "sources": [],
            },
        )
        current["confidence"] = max(float(current["confidence"]), 0.75)
        if "reverse-impact-candidate" not in current["reasons"]:
            current["reasons"].append("reverse-impact-candidate")

    result = list(ranked.values())
    for item in result:
        item["confidence"] = round(float(item["confidence"]), 3)
        item["reasons"] = sorted(item["reasons"])
        item["sources"] = sorted(item["sources"])
    result.sort(key=lambda item: (-float(item["confidence"]), item["test"]))
    return result[: max(1, limit)]


def check_contracts() -> None:
    path = base.CONFIG_DIR / "test-evidence-contract.json"
    if not path.is_file():
        raise RuntimeError("missing repo-intel test evidence contract")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if int(payload.get("max_transitive_depth", 0)) != MAX_TRANSITIVE_DEPTH:
        raise RuntimeError("test-evidence transitive-depth contract drifted")
    if payload.get("confidence_semantics") != "structural relevance only":
        raise RuntimeError("test-evidence confidence semantics drifted")
    print(f"repo-intel-test-evidence: contract valid (depth={MAX_TRANSITIVE_DEPTH})")


if __name__ == "__main__":
    print("repo_intel_test_evidence is a library layer; use scripts/repo_intel_frontier.py", file=sys.stderr)
    raise SystemExit(2)
