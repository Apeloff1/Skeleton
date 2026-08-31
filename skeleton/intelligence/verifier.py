"""Code verifier — a critique pass over generated artefacts before they ship.

Direction-A research (frontier → production, 2026): verifier-model loops —
a second, cheaper pass that scores generated code against a rubric before
acceptance — are the single biggest reliability win for code generation,
beating bigger generators. This verifier is a rule-based rubric so it runs
with no model: the generator stays the LM; the check is mechanical and
deterministic.

Rubric dimensions (each 0..1, weighted):
- syntax     — balanced delimiters/quotes, no obvious truncation
- structure  — expected constructs present (def/class/return for code)
- safety     — no eval/exec, no bare except, no shell injection vectors
- size       — non-trivial but not bloated for the ask
- grounding  — identifiers from the request actually appear

Compose with ``intelligence/verification.VerificationLoop`` for a
revise-until-green loop, or call once as a pre-accept gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Sequence, Tuple

from skeleton.intelligence.verification import VerificationVerdict


@dataclass(frozen=True)
class RubricScore:
    dimension: str
    score: float
    note: str = ""


@dataclass(frozen=True)
class VerifierReport:
    score: float
    dimensions: Tuple[RubricScore, ...]
    issues: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "dimensions": [vars(d) for d in self.dimensions],
            "issues": list(self.issues),
        }


_UNSAFE = re.compile(r"\b(eval|exec)\s*\(|except\s*:|os\.system|subprocess\.", re.M)


def _balanced(text: str) -> bool:
    stack: List[str] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    for ch in text:
        if ch in "([{":
            stack.append(ch)
        elif ch in pairs:
            if not stack or stack.pop() != pairs[ch]:
                return False
    return not stack


class CodeVerifier:
    """Rubric-based verification of generated code — the pre-accept gate."""

    def __init__(self, *, accept_at: float = 0.7) -> None:
        self.accept_at = accept_at
        self.checks = 0
        self.accepted = 0

    def verify(self, code: str, *, request: str = "") -> VerifierReport:
        self.checks += 1
        dims: List[RubricScore] = []
        issues: List[str] = []

        # syntax
        syntax_ok = _balanced(code)
        dims.append(RubricScore("syntax", 1.0 if syntax_ok else 0.0,
                                "balanced delimiters" if syntax_ok else "unbalanced delimiters"))
        if not syntax_ok:
            issues.append("unbalanced delimiters")

        # structure
        has_def = "def " in code or "class " in code
        has_return = "return" in code or "=" in code
        structure = (0.6 if has_def else 0.0) + (0.4 if has_return else 0.0)
        dims.append(RubricScore("structure", structure))
        if not has_def:
            issues.append("no function or class definition")

        # safety
        unsafe = _UNSAFE.findall(code)
        safety = 1.0 if not unsafe else 0.0
        dims.append(RubricScore("safety", safety))
        if unsafe:
            issues.append(f"unsafe constructs: {sorted(set(unsafe))}")

        # size — non-trivial, not bloated
        lines = [l for l in code.splitlines() if l.strip()]
        size = 1.0 if 3 <= len(lines) <= 400 else (0.5 if lines else 0.0)
        dims.append(RubricScore("size", size))

        # grounding — request identifiers appear in the code
        grounding = 1.0
        if request:
            anchors = [w for w in re.findall(r"[A-Za-z_]{4,}", request.lower())
                       if w not in {"that", "with", "this", "from", "function", "should"}]
            if anchors:
                hits = sum(1 for a in anchors if a in code.lower())
                grounding = hits / len(anchors)
                if grounding < 0.3:
                    issues.append("code ignores the request's named concepts")
        dims.append(RubricScore("grounding", grounding))

        score = (0.25 * dims[0].score + 0.20 * dims[1].score +
                 0.25 * dims[2].score + 0.10 * dims[3].score +
                 0.20 * dims[4].score)
        if score >= self.accept_at:
            self.accepted += 1
        return VerifierReport(score=score, dimensions=tuple(dims),
                              issues=tuple(issues))

    def verdict(self, code: str, *, request: str = "") -> VerificationVerdict:
        """Adapter for VerificationLoop — report as a verification verdict."""
        report = self.verify(code, request=request)
        return VerificationVerdict(confidence=report.score, issues=report.issues)

    def stats(self) -> Dict[str, Any]:
        return {
            "checks": self.checks,
            "accepted": self.accepted,
            "accept_rate": round(self.accepted / max(1, self.checks), 4),
        }
