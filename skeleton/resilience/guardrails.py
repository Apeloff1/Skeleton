"""Output guardrails — split from the resilience monolith (v16.2)."""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional


class OutputGuardrail:
    """
    Semantic safety filters for generated output.
    Detects: PII leakage, harmful content, policy violations, hallucinations.
    """

    PII_PATTERNS = [
        r"\b\d{3}-\d{2}-\d{4}\b",  # SSN
        r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",  # Credit card
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # Email
        r"\b\d{3}-\d{3}-\d{4}\b",  # Phone
    ]

    HARM_INDICATORS = [
        "how to make", "instructions for", "step by step", "recipe for",
        "tutorial on", "guide to", "method for",
    ]

    def __init__(self) -> None:
        self._pii_regex = [re.compile(p) for p in self.PII_PATTERNS]
        self._history: List[Dict[str, Any]] = []

    def evaluate(self, output: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        violations: List[str] = []
        score = 0.0
        redacted = output

        pii_found = False
        for pattern in self._pii_regex:
            if pattern.search(output):
                pii_found = True
                violations.append(f"PII detected: {pattern.pattern[:30]}")
                redacted = pattern.sub("[REDACTED]", redacted)
        if pii_found:
            score += 0.4

        for indicator in self.HARM_INDICATORS:
            if indicator.lower() in output.lower():
                dangerous = ["weapon", "bomb", "drug", "poison", "hack", "exploit"]
                for term in dangerous:
                    if term in output.lower():
                        violations.append(f"Potentially harmful: {indicator} + {term}")
                        score += 0.3

        hallucination_score = self._detect_hallucinations(output)
        if hallucination_score > 0.5:
            violations.append(f"Possible hallucination: score {hallucination_score:.3f}")
            score += 0.2

        result = {
            "safe": score < 0.5,
            "score": min(score, 1.0),
            "violations": violations,
            "redacted_output": redacted if redacted != output else None,
            "timestamp": time.time(),
        }
        self._history.append(result)
        return result

    def _detect_hallucinations(self, text: str) -> float:
        score = 0.0
        specific_patterns = [
            r"\b\d{4}\b",
            r"\b\d+\.\d+\b",
            r"according to [A-Z][a-z]+ \(\d{4}\)",
        ]
        has_citations = bool(re.search(r"\([A-Z][a-z]+,? \d{4}\)", text))
        has_specifics = any(re.search(p, text) for p in specific_patterns[:2])
        if has_specifics and not has_citations:
            score += 0.5
        contradiction_words = ["however", "but", "although", "contrary", "despite"]
        if sum(1 for w in contradiction_words if w in text.lower()) > 3:
            score += 0.2
        return min(score, 1.0)
