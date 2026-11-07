"""Unicode script-aware retrieval coverage and term matching limitations.

Heuristic scripts derived from Unicode character names are *not* a language
detector. Multi-script material should not be treated as inherently malicious.
Source-only analysis measures whether the operator query vocabulary might
systematically omit non-Latin selected text. Never translate or call a model.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
import unicodedata

from ..contracts import digest
from ..objectives import ObjectivePlan
from .frames import FrameSet


_RECOGNIZED = ("LATIN", "CYRILLIC", "GREEK", "ARABIC", "HEBREW",
               "DEVANAGARI", "BENGALI", "HIRAGANA", "KATAKANA",
               "HANGUL", "CJK", "THAI", "GEORGIAN", "ARMENIAN")


def _script(character: str) -> str | None:
    if not unicodedata.category(character).startswith("L"):
        return None
    name = unicodedata.name(character, "")
    for script in _RECOGNIZED:
        if name.startswith(script + " "):
            return script.lower()
    return "unclassified_letter_script"


@dataclass(frozen=True)
class ScriptCoverageFinding:
    objective_id: str
    scripts_observed: tuple[str, ...]
    non_latin_letter_count: int
    latin_letter_count: int
    selected_source_count: int
    non_latin_source_count: int
    operator_term_ascii_only: bool
    non_latin_selected_evidence: bool
    lexical_coverage_review: bool
    external_translation_run: bool = False
    language_identified: bool = False


@dataclass(frozen=True)
class ScriptCoverageReport:
    frame_set_digest: str
    objective_plan_digest: str
    findings: tuple[ScriptCoverageFinding, ...]
    review_objectives: tuple[str, ...]
    inspected_letters: int
    report_digest: str
    language_certainty_assessed: bool = False
    external_text_translated: bool = False
    new_query_executed: bool = False


def inspect_script_coverage(
    frames: FrameSet, plan: ObjectivePlan,
    *, min_non_latin_letters: int = 5,
) -> ScriptCoverageReport:
    if not isinstance(frames, FrameSet) or not isinstance(plan, ObjectivePlan):
        raise TypeError("typed operator objectives and source frames required")
    if frames.mandate_digest != plan.mandate_digest:
        raise PermissionError("foreign operator objective for script coverage")
    if type(min_non_latin_letters) is not int or not 1 <= min_non_latin_letters <= 100:
        raise ValueError("invalid script evidence threshold")
    goals = {g.objective_id: g for g in plan.objectives}
    sources = defaultdict(set)
    hosts_with_nonlatin = defaultdict(set)
    counters = defaultdict(Counter)
    for frame in frames.frames:
        if not set(frame.anchor.objective_ids) <= set(goals):
            raise PermissionError("unapproved operator objective in selected script evidence")
        tokens = Counter()
        for character in frame.text:
            script = _script(character)
            if script is not None:
                tokens[script] += 1
        for goal_id in frame.anchor.objective_ids:
            counters[goal_id].update(tokens)
            sources[goal_id].add(frame.anchor.source_id)
            if sum(count for script, count in tokens.items() if script != "latin") >= min_non_latin_letters:
                hosts_with_nonlatin[goal_id].add(frame.anchor.source_id)
    findings = []
    held = []
    for goal in plan.objectives:
        current = counters[goal.objective_id]
        latin = current["latin"]
        other = sum(n for script, n in current.items() if script != "latin")
        ascii_terms = all(all(ord(char) < 128 for char in t)
                          for t in goal.required_terms + goal.blocked_terms)
        has_other = other >= min_non_latin_letters
        risk = bool(has_other and ascii_terms)
        if risk:
            held.append(goal.objective_id)
        findings.append(ScriptCoverageFinding(
            goal.objective_id, tuple(sorted(current)),
            other, latin, len(sources[goal.objective_id]),
            len(hosts_with_nonlatin[goal.objective_id]), ascii_terms,
            has_other, risk,
        ))
    payload = {
        "frames": frames.frame_set_digest, "plan": plan.plan_digest,
        "findings": [asdict(x) for x in findings],
        "min_nonlatin": min_non_latin_letters,
    }
    return ScriptCoverageReport(
        frames.frame_set_digest, plan.plan_digest, tuple(findings),
        tuple(held), sum(sum(counter.values()) for counter in counters.values()),
        digest(payload),
    )
