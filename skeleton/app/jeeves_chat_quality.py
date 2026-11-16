"""Independent, deterministic conversational qualification of captured answers.

This module evaluates externally collected actual answers. It never synthesizes
answers, calls a model, auto-promotes weights, or certifies semantic quality.
Human rubrics and exact execution receipts remain separate evidence.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Any, Iterable, Mapping

MAX_CASES = 25_000
MAX_ANSWER_BYTES = 256 * 1024
MAX_TURNS = 1000
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CASE = re.compile(r"[a-z0-9][a-z0-9_.-]{0,95}\Z")
SCHEMA = "skeleton.jeeves.chat-quality.v1"


class QualificationRejected(ValueError):
    pass


def _hash(text: str) -> str:
    return sha256(text.encode("utf-8", errors="strict")).hexdigest()


def _bounded_text(text: Any, limit: int) -> str:
    if not isinstance(text, str) or "\x00" in text:
        raise QualificationRejected("invalid text")
    try:
        if len(text.encode("utf-8", errors="strict")) > limit:
            raise QualificationRejected("text exceeds byte budget")
    except UnicodeError:
        raise QualificationRejected("invalid Unicode") from None
    return text


def _stable(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _strict_json(text: str) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def reject(_value):
        raise ValueError("invalid JSON constant")
    return json.loads(text, object_pairs_hook=pairs, parse_constant=reject)


@dataclass(frozen=True, slots=True)
class TurnSpec:
    prompt: str
    must_include: tuple[str, ...] = ()
    must_exclude: tuple[str, ...] = ()
    exact_answer: str | None = None
    max_words: int | None = None
    json_keys: tuple[str, ...] = ()
    human_rubric: str = ""

    def validate(self) -> None:
        if not _bounded_text(self.prompt, 32_768).strip():
            raise QualificationRejected("empty prompt")
        for values in (self.must_include, self.must_exclude, self.json_keys):
            if not isinstance(values, tuple) or len(values) > 32:
                raise QualificationRejected("invalid criterion inventory")
            if any(not _bounded_text(x, 2048) for x in values):
                raise QualificationRejected("empty criterion")
            if len(set(values)) != len(values):
                raise QualificationRejected("duplicate criterion")
        if {x.casefold() for x in self.must_include} & {x.casefold() for x in self.must_exclude}:
            raise QualificationRejected("contradictory criterion")
        if self.exact_answer is not None:
            _bounded_text(self.exact_answer, MAX_ANSWER_BYTES)
        if self.max_words is not None and (
            type(self.max_words) is not int or not 1 <= self.max_words <= MAX_ANSWER_BYTES
        ):
            raise QualificationRejected("invalid word budget")
        _bounded_text(self.human_rubric, 4096)
        if not any((self.must_include, self.must_exclude, self.exact_answer is not None,
                    self.max_words, self.json_keys, self.human_rubric)):
            raise QualificationRejected("unscored turn specification")

    def as_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in (
            "prompt", "must_include", "must_exclude", "exact_answer",
            "max_words", "json_keys", "human_rubric",
        )}


@dataclass(frozen=True, slots=True)
class Case:
    case_id: str
    category: str
    turns: tuple[TurnSpec, ...]

    def validate(self) -> None:
        if (not isinstance(self.case_id, str) or not _CASE.fullmatch(self.case_id)
                or not isinstance(self.category, str) or not _CASE.fullmatch(self.category)
                or not isinstance(self.turns, tuple) or not 1 <= len(self.turns) <= MAX_TURNS):
            raise QualificationRejected("invalid case")
        for item in self.turns:
            if not isinstance(item, TurnSpec):
                raise QualificationRejected("invalid turn")
            item.validate()

    def fingerprint(self) -> str:
        self.validate()
        return _hash(_stable({"case_id": self.case_id, "category": self.category,
                              "turns": [x.as_dict() for x in self.turns]}))


def evaluate_turn(spec: TurnSpec, answer: str) -> dict[str, Any]:
    spec.validate()
    answer = _bounded_text(answer, MAX_ANSWER_BYTES)
    folded = answer.casefold()
    checks = []
    for value in spec.must_include:
        checks.append(("required_literal", value.casefold() in folded))
    for value in spec.must_exclude:
        checks.append(("forbidden_literal", value.casefold() not in folded))
    if spec.exact_answer is not None:
        checks.append(("exact_answer", answer.strip() == spec.exact_answer))
    if spec.max_words is not None:
        checks.append(("word_budget", len(answer.split()) <= spec.max_words))
    if spec.json_keys:
        try:
            parsed = _strict_json(answer)
            valid = isinstance(parsed, dict) and set(parsed) == set(spec.json_keys)
        except (ValueError, RecursionError):
            valid = False
        checks.append(("closed_json_keys", valid))
    # A human-only turn cannot silently become a machine pass.
    return {
        "answer_sha256": _hash(answer),
        "checks": [{"criterion": k, "passed": v} for k, v in checks],
        "deterministic_passed": all(v for _, v in checks) if checks else None,
        "human_review_required": bool(spec.human_rubric),
        "semantic_quality_certified": False,
    }


def qualify(cases: Iterable[Case], captures: Iterable[Mapping[str, Any]], *,
            model_digest: str, protocol_digest: str) -> dict[str, Any]:
    """Require a complete matched inventory with content-bound capture identity.

    Execution receipt digests are externally supplied identifiers, not proof
    that a capture genuinely came from the model. No self-judge is accepted.
    """
    if not all(isinstance(v, str) and _SHA.fullmatch(v) for v in
               (model_digest, protocol_digest)):
        raise QualificationRejected("invalid model or protocol identity")
    registry = {}
    for count, case in enumerate(cases, 1):
        if count > MAX_CASES or not isinstance(case, Case):
            raise QualificationRejected("oversized or invalid case inventory")
        fingerprint = case.fingerprint()
        if case.case_id in registry:
            raise QualificationRejected("duplicate case")
        registry[case.case_id] = (case, fingerprint)
    if not registry:
        raise QualificationRejected("empty case inventory")
    expected_count = sum(len(case.turns) for case, _ in registry.values())
    seen = {}
    receipts = set()
    for count, row in enumerate(captures, 1):
        required = {"case_id", "case_sha256", "turn_index", "prompt_sha256",
                    "model_digest", "protocol_digest", "answer",
                    "answer_sha256", "execution_receipt_digest"}
        if count > expected_count or not isinstance(row, Mapping) or set(row) != required:
            raise QualificationRejected("unexpected capture")
        case_id = row["case_id"]
        if not isinstance(case_id, str) or case_id not in registry:
            raise QualificationRejected("foreign capture")
        case, fingerprint = registry[case_id]
        index = row["turn_index"]
        if type(index) is not int or not 0 <= index < len(case.turns):
            raise QualificationRejected("invalid turn index")
        key = (case_id, index)
        if key in seen:
            raise QualificationRejected("duplicate capture")
        receipt = row["execution_receipt_digest"]
        if (row["case_sha256"] != fingerprint
                or row["model_digest"] != model_digest
                or row["protocol_digest"] != protocol_digest
                or row["prompt_sha256"] != _hash(case.turns[index].prompt)
                or type(receipt) is not str or not _SHA.fullmatch(receipt)
                or receipt in receipts):
            raise QualificationRejected("capture identity mismatch")
        score = evaluate_turn(case.turns[index], row["answer"])
        if row["answer_sha256"] != score["answer_sha256"]:
            raise QualificationRejected("answer identity mismatch")
        receipts.add(receipt)
        seen[key] = {"case_id": case_id, "case_sha256": fingerprint,
                     "category": case.category, "turn_index": index,
                     "execution_receipt_digest": receipt, **score}
    if len(seen) != expected_count:
        raise QualificationRejected("incomplete turn inventory")
    by_category = defaultdict(lambda: {"scored": 0, "passed": 0, "human_review_pending": 0})
    for item in seen.values():
        group = by_category[item["category"]]
        if item["deterministic_passed"] is not None:
            group["scored"] += 1
            group["passed"] += int(item["deterministic_passed"])
        group["human_review_pending"] += int(item["human_review_required"])
    manifest = [(key, value[1]) for key, value in sorted(registry.items())]
    report = {
        "schema": SCHEMA, "model_digest": model_digest,
        "protocol_digest": protocol_digest, "suite_sha256": _hash(_stable(manifest)),
        "cases": len(registry), "turns": expected_count,
        "categories": dict(sorted(by_category.items())),
        "turn_results": [seen[key] for key in sorted(seen)],
        "external_receipts_independently_verified": False,
        "semantic_quality_certified": False,
        "model_promotion_authorized": False,
    }
    report["report_sha256"] = _hash(_stable(report))
    return report


def compare(left: Mapping[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    """Matched deterministic score deltas; never a cross-protocol leaderboard."""
    for report in (left, right):
        if report.get("schema") != SCHEMA or not isinstance(report.get("report_sha256"), str):
            raise QualificationRejected("invalid report")
        unhashed = {k: v for k, v in report.items() if k != "report_sha256"}
        if _hash(_stable(unhashed)) != report["report_sha256"]:
            raise QualificationRejected("report digest mismatch")
    if any(left[key] != right[key] for key in ("suite_sha256", "protocol_digest", "cases", "turns")):
        raise QualificationRejected("unmatched evaluation protocols")
    if set(left["categories"]) != set(right["categories"]):
        raise QualificationRejected("unmatched categories")
    deltas = {}
    for category, a in left["categories"].items():
        b = right["categories"][category]
        if a["scored"] != b["scored"] or a["human_review_pending"] != b["human_review_pending"]:
            raise QualificationRejected("unmatched scoring inventory")
        deltas[category] = {
            "scored": a["scored"], "left_passed": a["passed"],
            "right_passed": b["passed"],
            "delta_percentage_points": (
                100 * (b["passed"] - a["passed"]) / a["scored"] if a["scored"] else None
            ),
            "human_review_pending": a["human_review_pending"],
        }
    return {"left_model_digest": left["model_digest"], "right_model_digest": right["model_digest"],
            "suite_sha256": left["suite_sha256"], "protocol_digest": left["protocol_digest"],
            "categories": deltas, "semantic_quality_certified": False}
