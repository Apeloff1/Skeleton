"""Source-only lexical constraint diagnostics for operator research objectives.

Checks which required/blocked operator terms are actually present in selected
retained passages, and records evidence deficits without trusting source text
or asserting factual answerability. No client text becomes an instruction.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import re
import unicodedata

from ..contracts import digest
from ..objectives import ObjectivePlan
from .frames import FrameSet

_WORD = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True)
class ObjectiveGrounding:
    objective_id: str
    selected_passages: int
    exact_required_term_passages: int
    prohibited_term_passages: int
    distinct_selected_sources: int
    distinct_selected_hosts: int
    reviewable_target: int
    lexical_passage_shortfall: int
    missing_evidence_review: bool
    lexical_match_proves_claim: bool = False


@dataclass(frozen=True)
class ObjectiveGroundingReport:
    frame_set_digest: str
    objective_plan_digest: str
    objectives: tuple[ObjectiveGrounding, ...]
    missing_or_weak_objectives: tuple[str, ...]
    prohibited_objectives: tuple[str, ...]
    report_digest: str
    factual_answerability_certified: bool = False
    untrusted_page_text_exported: bool = False


def inspect_objective_grounding(
    frames: FrameSet, plan: ObjectivePlan,
) -> ObjectiveGroundingReport:
    if not isinstance(frames, FrameSet) or not isinstance(plan, ObjectivePlan):
        raise TypeError("operator objectives and exact source frames required")
    if frames.mandate_digest != plan.mandate_digest:
        raise PermissionError("cross-mandate objective grounding")
    targets = {row.objective_id: row for row in plan.objectives}
    counts = defaultdict(lambda: [0, 0, 0, set(), set()])
    for frame in frames.frames:
        anchor = frame.anchor
        words = set(_WORD.findall(unicodedata.normalize("NFKC", frame.text).casefold()))
        for objective_id in anchor.objective_ids:
            if objective_id not in targets:
                raise PermissionError("selected passage is outside operator objective scope")
            goal = targets[objective_id]
            n = counts[objective_id]
            n[0] += 1
            n[3].add(anchor.source_id)
            n[4].add(anchor.host)
            required = set(goal.required_terms)
            blocked = set(goal.blocked_terms)
            if required <= words and not blocked & words:
                n[1] += 1
            if blocked & words:
                n[2] += 1
    results = []
    missing = []
    prohibited = []
    for item in plan.objectives:
        count, exact, negative, sources, hosts = counts[item.objective_id]
        shortfall = max(0, item.minimum_reviewable_passages - exact)
        missing_review = bool(shortfall or not sources)
        if missing_review:
            missing.append(item.objective_id)
        if negative:
            prohibited.append(item.objective_id)
        results.append(ObjectiveGrounding(
            item.objective_id, count, exact, negative, len(sources), len(hosts),
            item.minimum_reviewable_passages, shortfall, missing_review,
        ))
    payload = {
        "frames": frames.frame_set_digest,
        "plan": plan.plan_digest,
        "objectives": [asdict(x) for x in results],
    }
    return ObjectiveGroundingReport(
        frames.frame_set_digest, plan.plan_digest, tuple(results),
        tuple(missing), tuple(prohibited), digest(payload),
    )
