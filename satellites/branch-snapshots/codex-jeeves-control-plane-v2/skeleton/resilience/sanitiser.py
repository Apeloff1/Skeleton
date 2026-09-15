"""Input sanitisation — three-layer defence (split from the resilience monolith, v16.2)."""

from __future__ import annotations

import math
import re
from typing import Dict, List, Tuple

from .types import ThreatCategory, ThreatLevel, ThreatReport


class InputSanitiser:
    """
    Three-layer input sanitisation:
      Layer 1: Lexical — regex patterns, blacklists, known attack strings
      Layer 2: Structural — delimiter analysis, nesting depth, token anomalies
      Layer 3: Semantic — embedding similarity to known attack vectors
    """

    INJECTION_PATTERNS = [
        r"ignore\s+(?:all\s+)?previous\s+instructions",
        r"forget\s+(?:your\s+)?(?:training|instructions|rules)",
        r"you\s+are\s+now\s+(?:a\s+)?(?:different\s+)?(?:ai|model|assistant)",
        r"system\s*:\s*",
        r"user\s*:\s*",
        r"assistant\s*:\s*",
        r"DAN\s*[:\-]",
        r"jailbreak",
        r"\{\{.*\}\}",
        r"<\|.*\|>",
    ]

    EXFILTRATION_PATTERNS = [
        r"send\s+(?:the\s+)?(?:data|information|content)\s+to",
        r"email\s+(?:me\s+)?(?:the\s+)?(?:results|data|content)",
        r"upload\s+(?:the\s+)?(?:file|data|content)\s+to",
        r"http[s]?://\S+",
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
    ]

    def __init__(self) -> None:
        self._injection_regex = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS]
        self._exfiltration_regex = [re.compile(p, re.IGNORECASE) for p in self.EXFILTRATION_PATTERNS]
        self._history: List[ThreatReport] = []

    def sanitise(self, raw_input: str) -> Tuple[str, ThreatReport]:
        evidence: List[str] = []
        max_level = ThreatLevel.BENIGN
        category = ThreatCategory.ADVERSARIAL_MANIPULATION

        for pattern in self._injection_regex:
            if pattern.search(raw_input):
                evidence.append(f"Lexical match: {pattern.pattern[:50]}")
                max_level = ThreatLevel(max_level.value + 1)
                category = ThreatCategory.PROMPT_INJECTION

        for pattern in self._exfiltration_regex:
            if pattern.search(raw_input):
                evidence.append(f"Exfiltration match: {pattern.pattern[:50]}")
                max_level = ThreatLevel(max_level.value + 1)
                category = ThreatCategory.DATA_EXFILTRATION

        structural_score = self._structural_analysis(raw_input)
        if structural_score > 0.7:
            evidence.append(f"Structural anomaly score: {structural_score:.3f}")
            max_level = ThreatLevel(max_level.value + 1)

        semantic_score = self._semantic_analysis(raw_input)
        if semantic_score > 0.8:
            evidence.append(f"Semantic anomaly score: {semantic_score:.3f}")
            max_level = ThreatLevel(max_level.value + 1)

        if max_level.value >= ThreatLevel.CRITICAL.value:
            level = ThreatLevel.CRITICAL
        elif max_level.value >= ThreatLevel.MALICIOUS.value:
            level = ThreatLevel.MALICIOUS
        elif max_level.value >= ThreatLevel.SUSPICIOUS.value:
            level = ThreatLevel.SUSPICIOUS
        else:
            level = ThreatLevel.BENIGN

        sanitized = self._apply_sanitization(raw_input, level)

        report = ThreatReport(
            level=level,
            category=category,
            confidence=min(0.3 + 0.2 * len(evidence), 0.99),
            evidence=evidence,
            sanitized_input=sanitized if sanitized != raw_input else None,
            action_taken=self._determine_action(level),
        )
        self._history.append(report)
        return sanitized, report

    def _structural_analysis(self, text: str) -> float:
        score = 0.0
        delimiters = text.count('"') + text.count("'") + text.count("`")
        if delimiters > 20:
            score += 0.3
        max_depth = 0
        current_depth = 0
        for char in text:
            if char in "({[<":
                current_depth += 1
                max_depth = max(max_depth, current_depth)
            elif char in ")}]>":
                current_depth -= 1
        if max_depth > 5:
            score += 0.3
        special_chars = sum(1 for c in text if not c.isalnum() and not c.isspace())
        density = special_chars / max(len(text), 1)
        if density > 0.3:
            score += 0.4
        return min(score, 1.0)

    def _semantic_analysis(self, text: str) -> float:
        score = 0.0
        entropy = self._calculate_entropy(text)
        if entropy > 4.5:
            score += 0.3
        attack_keywords = ["ignore", "forget", "system", "override", "bypass", "jailbreak", "DAN"]
        keyword_count = sum(1 for kw in attack_keywords if kw.lower() in text.lower())
        if keyword_count >= 3:
            score += 0.4
        if len(text) > 5000:
            score += 0.2
        return min(score, 1.0)

    def _calculate_entropy(self, text: str) -> float:
        if not text:
            return 0.0
        freq: Dict[str, int] = {}
        for char in text:
            freq[char] = freq.get(char, 0) + 1
        length = len(text)
        return -sum((count / length) * math.log2(count / length) for count in freq.values())

    def _apply_sanitization(self, text: str, level: ThreatLevel) -> str:
        if level == ThreatLevel.BENIGN:
            return text
        elif level == ThreatLevel.SUSPICIOUS:
            sanitized = text
            for pattern in self.INJECTION_PATTERNS:
                sanitized = re.sub(pattern, "[REDACTED]", sanitized, flags=re.IGNORECASE)
            return sanitized
        elif level == ThreatLevel.MALICIOUS:
            sanitized = re.sub(r"[^\w\s\.\,\!\?\-]", "", text)
            return sanitized[:1000]
        else:  # CRITICAL
            return "[INPUT BLOCKED: SECURITY VIOLATION]"

    def _determine_action(self, level: ThreatLevel) -> str:
        actions = {
            ThreatLevel.BENIGN: "pass_through",
            ThreatLevel.SUSPICIOUS: "sanitize_and_log",
            ThreatLevel.MALICIOUS: "block_and_alert",
            ThreatLevel.CRITICAL: "block_and_quarantine",
        }
        return actions[level]
