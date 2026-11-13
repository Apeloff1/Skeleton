from __future__ import annotations

from collections import Counter
from typing import Sequence

from .verdict import CaseResult, aggregate


def to_json(results: Sequence[CaseResult], head_sha: str) -> dict:
    counts = Counter(r.verdict.value for r in results)
    return {
        "schema": "gfm-qualification-report/v1",
        "source_verification": "self-declared-JSON-not-independent-attestation",
        "native_device_qualified": False,
        "release_certified": False,
        "head_sha": head_sha,
        "overall": aggregate(results).value,
        "counts": {k: counts.get(k, 0) for k in ("pass", "fail", "blocked")},
        "results": [r.to_dict() for r in results],
    }


def to_markdown(results: Sequence[CaseResult], head_sha: str) -> str:
    doc = to_json(results, head_sha)
    lines = [
        f"# GF-M qualification report — `{head_sha[:12]}`",
        "",
        f"Overall: **{doc['overall'].upper()}** "
        f"(pass {doc['counts']['pass']}, fail {doc['counts']['fail']}, blocked {doc['counts']['blocked']})",
        "",
        "| Case | Gate | Verdict | Reasons |",
        "|---|---|---|---|",
    ]
    for r in results:
        reasons = "; ".join(r.reasons).replace("|", "\\|") or "—"
        lines.append(f"| {r.case_id} | {r.gate} | {r.verdict.value} | {reasons} |")
    return "\n".join(lines) + "\n"
