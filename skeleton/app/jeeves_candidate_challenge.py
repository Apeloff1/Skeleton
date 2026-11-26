"""Bounded, independent structural adversarial review of actual candidates.

These diagnostics are not semantic entailment, a learned judge, or a score.
They surface literal disagreement, omitted coverage, and source audit
failures without turning model text into instructions or choosing a winner.
"""
from __future__ import annotations

from hashlib import sha256
import itertools
import json
import re
import unicodedata

SCHEMA = "skeleton.jeeves.candidate-challenge.v1"
MAX_CANDIDATES = 4
MAX_SEGMENTS = 64
MAX_CHARS = 16384
MAX_COMPARISONS = 96
_NUMBER = re.compile(r"(?<![\w.])[-+]?(?:[0-9]+(?:\.[0-9]+)?)(?![\w.])")
_SPLIT = re.compile(r"(?<=[.!?。！？])\s+|\n+")
_CITATION = re.compile(r"local:[A-Za-z0-9_-]{1,100}:[0-9]+:[0-9a-f]{16}")
_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                             separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _text_sha(value):
    return sha256(value.encode("utf-8")).hexdigest()


def _segments(text):
    rows = []
    cursor = 0
    for boundary in list(_SPLIT.finditer(text))[:MAX_SEGMENTS]:
        start, end = cursor, boundary.start()
        if start < end and text[start:end].strip():
            rows.append((start, end, text[start:end]))
        cursor = boundary.end()
    if cursor < len(text) and len(rows) < MAX_SEGMENTS:
        rows.append((cursor, len(text), text[cursor:]))
    return rows[:MAX_SEGMENTS], len(_SPLIT.findall(text)) + 1 > MAX_SEGMENTS


def _numbers(text):
    normalized = unicodedata.normalize("NFKC", _CITATION.sub(" ", text)).casefold()
    values = tuple(m.group() for m in _NUMBER.finditer(normalized))
    if not values or len(values) > 8:
        return None
    # Keep word order, units, polarity, and every other token. Only numeric
    # literal positions are abstracted; never pair unrelated lexical claims.
    template = " ".join(_NUMBER.sub(" <number> ", normalized).split())
    if len(_WORD.findall(template)) < 4:
        return None
    return template, values


def examine(candidates):
    if type(candidates) is not list or not 1 <= len(candidates) <= MAX_CANDIDATES:
        raise ValueError("bounded candidate review required")
    indices, summaries, lookup = [], [], []
    for index, row in enumerate(candidates):
        text = row.get("text")
        if (type(text) is not str or not text.strip() or len(text.encode("utf-8")) > MAX_CHARS
                or row.get("output_sha256") != _text_sha(text)):
            raise ValueError("candidate text identity mismatch")
        parts, truncated = _segments(text)
        templates = {}
        for start, end, segment in parts:
            numeric = _numbers(segment)
            if numeric is None:
                continue
            template, values = numeric
            templates.setdefault(template, []).append((start, end, values))
        lookup.append(templates)
        faith = row.get("faithfulness")
        audits = row.get("citation_audit")
        status = {}
        if isinstance(faith, dict) and isinstance(faith.get("claims"), list):
            for claim in faith["claims"]:
                key = claim["status"]
                status[key] = status.get(key, 0)+1
        indices.append(row["output_sha256"])
        summaries.append({
            "candidate_index": index, "output_sha256": row["output_sha256"],
            "segments_examined": len(parts), "segment_scan_truncated": truncated,
            "source_audit_disposition": None if faith is None else faith["disposition"],
            "source_claim_status_counts": status,
            "citation_identifier_status": None if audits is None else audits["status"],
            "explicit_contract_passed": (row["verification"].get("passed")
                                         if isinstance(row.get("verification"), dict) else None),
        })
    conflicts = []
    comparisons = 0
    capped = False
    for a, b in itertools.combinations(range(len(candidates)), 2):
        for template in sorted(set(lookup[a]) & set(lookup[b])):
            for left, right in itertools.product(lookup[a][template], lookup[b][template]):
                if comparisons >= MAX_COMPARISONS:
                    capped = True
                    break
                comparisons += 1
                if left[2] != right[2]:
                    def span(index, item):
                        start, end, values = item
                        return {"candidate_index": index, "start": start, "end": end,
                                "segment_sha256": _text_sha(candidates[index]["text"][start:end]),
                                "numeric_literals": list(values)}
                    conflicts.append({"method": "same_normalized_template_different_literals",
                                      "template_sha256": _text_sha(template),
                                      "left": span(a,left), "right": span(b,right)})
            if capped:
                break
        if capped:
            break
    result = {"schema": SCHEMA, "candidate_sha256": indices,
              "distinct_exact_outputs": len(set(indices)), "candidates": summaries,
              "numeric_disagreements": conflicts, "comparisons": comparisons,
              "comparison_cap_reached": capped,
              "all_claims_examined": False, "semantic_contradiction_verified": False,
              "confidence_calibrated": False, "winner_selected": False}
    result["receipt_sha256"] = digest(result)
    return result
