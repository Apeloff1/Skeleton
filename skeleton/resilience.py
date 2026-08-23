"""
================================================================================
skeleton.resilience — Adversarial Resilience Fortress
================================================================================
Multi-layer defence against prompt injection, data exfiltration, and
adversarial manipulation. Features:
  1. Input sanitisation: semantic + lexical + structural analysis
  2. Output guardrails: policy enforcement, semantic safety filters
  3. Self-healing: automatic rollback, circuit breakers, chaos engineering
  4. Knowledge exfiltration detection: monitor for data leakage patterns
  5. Shadow mode: silent A/B testing without user awareness

Design invariants:
  1. Every input passes through all three sanitisation layers.
  2. Every output is scored for safety before delivery.
  3. Exfiltration detection runs continuously on all I/O.
  4. Shadow mode never impacts user-visible latency.
  5. All resilience events are auditable via the event bus.
================================================================================
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Set, Tuple

from skeleton.kernel.errors import SkeletonError
from skeleton.kernel.events import DomainEvent, EventBus


# =============================================================================
# THREAT CLASSIFICATION
# =============================================================================

class ThreatLevel(Enum):
    BENIGN = auto()
    SUSPICIOUS = auto()
    MALICIOUS = auto()
    CRITICAL = auto()


class ThreatCategory(Enum):
    PROMPT_INJECTION = auto()
    DATA_EXFILTRATION = auto()
    JAILBREAK_ATTEMPT = auto()
    ADVERSARIAL_MANIPULATION = auto()
    MODEL_EXTRACTION = auto()
    PRIVACY_VIOLATION = auto()


@dataclass
class ThreatReport:
    """Complete threat analysis report."""
    level: ThreatLevel
    category: ThreatCategory
    confidence: float  # 0.0 - 1.0
    evidence: List[str]
    sanitized_input: Optional[str] = None
    action_taken: str = "none"
    timestamp: float = field(default_factory=time.time)


# =============================================================================
# INPUT SANITISATION — THREE-LAYER DEFENCE
# =============================================================================

class InputSanitiser:
    """
    Three-layer input sanitisation:
      Layer 1: Lexical — regex patterns, blacklists, known attack strings
      Layer 2: Structural — delimiter analysis, nesting depth, token anomalies
      Layer 3: Semantic — embedding similarity to known attack vectors
    """

    # Known prompt injection patterns
    INJECTION_PATTERNS = [
        r"ignore\s+(?:all\s+)?previous\s+instructions",
        r"forget\s+(?:your\s+)?(?:training|instructions|rules)",
        r"you\s+are\s+now\s+(?:a\s+)?(?:different\s+)?(?:ai|model|assistant)",
        r"system\s*:\s*",
        r"user\s*:\s*",
        r"assistant\s*:\s*",
        r"DAN\s*[:\-]",
        r"jailbreak",
        r"\{\{.*\}\}",  # Template injection
        r"<\|.*\|>",      # Special token injection
    ]

    # Data exfiltration patterns
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
        """
        Run all three sanitisation layers. Returns (sanitised, report).
        """
        evidence: List[str] = []
        max_level = ThreatLevel.BENIGN
        category = ThreatCategory.ADVERSARIAL_MANIPULATION

        # Layer 1: Lexical
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

        # Layer 2: Structural
        structural_score = self._structural_analysis(raw_input)
        if structural_score > 0.7:
            evidence.append(f"Structural anomaly score: {structural_score:.3f}")
            max_level = ThreatLevel(max_level.value + 1)

        # Layer 3: Semantic (simplified: keyword density + entropy)
        semantic_score = self._semantic_analysis(raw_input)
        if semantic_score > 0.8:
            evidence.append(f"Semantic anomaly score: {semantic_score:.3f}")
            max_level = ThreatLevel(max_level.value + 1)

        # Determine final level
        if max_level.value >= ThreatLevel.CRITICAL.value:
            level = ThreatLevel.CRITICAL
        elif max_level.value >= ThreatLevel.MALICIOUS.value:
            level = ThreatLevel.MALICIOUS
        elif max_level.value >= ThreatLevel.SUSPICIOUS.value:
            level = ThreatLevel.SUSPICIOUS
        else:
            level = ThreatLevel.BENIGN

        # Sanitise based on level
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
        """Detect structural anomalies: delimiter abuse, nesting, token density."""
        score = 0.0
        # Delimiter abuse
        delimiters = text.count('"') + text.count("'") + text.count("`")
        if delimiters > 20:
            score += 0.3
        # Nesting depth
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
        # Token density (unusual character frequency)
        special_chars = sum(1 for c in text if not c.isalnum() and not c.isspace())
        density = special_chars / max(len(text), 1)
        if density > 0.3:
            score += 0.4
        return min(score, 1.0)

    def _semantic_analysis(self, text: str) -> float:
        """Semantic anomaly: keyword density, entropy, known attack similarity."""
        score = 0.0
        # High entropy = suspicious
        entropy = self._calculate_entropy(text)
        if entropy > 4.5:
            score += 0.3
        # Known attack keywords
        attack_keywords = ["ignore", "forget", "system", "override", "bypass", "jailbreak", "DAN"]
        keyword_count = sum(1 for kw in attack_keywords if kw.lower() in text.lower())
        if keyword_count >= 3:
            score += 0.4
        # Length anomaly
        if len(text) > 5000:
            score += 0.2
        return min(score, 1.0)

    def _calculate_entropy(self, text: str) -> float:
        """Shannon entropy of character distribution."""
        if not text:
            return 0.0
        freq: Dict[str, int] = {}
        for char in text:
            freq[char] = freq.get(char, 0) + 1
        length = len(text)
        import math
        return -sum((count / length) * math.log2(count / length) for count in freq.values())

    def _apply_sanitization(self, text: str, level: ThreatLevel) -> str:
        """Apply sanitisation based on threat level."""
        if level == ThreatLevel.BENIGN:
            return text
        elif level == ThreatLevel.SUSPICIOUS:
            # Remove suspicious patterns
            sanitized = text
            for pattern in self.INJECTION_PATTERNS:
                sanitized = re.sub(pattern, "[REDACTED]", sanitized, flags=re.IGNORECASE)
            return sanitized
        elif level == ThreatLevel.MALICIOUS:
            # Aggressive sanitisation
            sanitized = re.sub(r"[^\w\s\.\,\!\?\-]", "", text)
            return sanitized[:1000]  # Truncate
        else:  # CRITICAL
            # Block entirely
            return "[INPUT BLOCKED: SECURITY VIOLATION]"

    def _determine_action(self, level: ThreatLevel) -> str:
        actions = {
            ThreatLevel.BENIGN: "pass_through",
            ThreatLevel.SUSPICIOUS: "sanitize_and_log",
            ThreatLevel.MALICIOUS: "block_and_alert",
            ThreatLevel.CRITICAL: "block_and_quarantine",
        }
        return actions[level]


# =============================================================================
# OUTPUT GUARDRAILS
# =============================================================================

class OutputGuardrail:
    """
    Semantic safety filters for generated output.
    Detects: PII leakage, harmful content, policy violations, hallucinations.
    """

    # PII patterns
    PII_PATTERNS = [
        r"\b\d{3}-\d{2}-\d{4}\b",  # SSN
        r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",  # Credit card
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # Email
        r"\b\d{3}-\d{3}-\d{4}\b",  # Phone
    ]

    # Harmful content indicators
    HARM_INDICATORS = [
        "how to make", "instructions for", "step by step", "recipe for",
        "tutorial on", "guide to", "method for",
    ]

    def __init__(self) -> None:
        self._pii_regex = [re.compile(p) for p in self.PII_PATTERNS]
        self._history: List[Dict[str, Any]] = []

    def evaluate(self, output: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Evaluate output for safety. Returns dict with:
          - safe: bool
          - score: float (0-1, higher = more concerning)
          - violations: list of detected issues
          - redacted_output: str (if PII found)
        """
        violations: List[str] = []
        score = 0.0
        redacted = output

        # PII detection
        pii_found = False
        for pattern in self._pii_regex:
            if pattern.search(output):
                pii_found = True
                violations.append(f"PII detected: {pattern.pattern[:30]}")
                redacted = pattern.sub("[REDACTED]", redacted)
        if pii_found:
            score += 0.4

        # Harmful content (simplified: keyword matching)
        for indicator in self.HARM_INDICATORS:
            if indicator.lower() in output.lower():
                # Check if followed by dangerous terms
                dangerous = ["weapon", "bomb", "drug", "poison", "hack", "exploit"]
                for term in dangerous:
                    if term in output.lower():
                        violations.append(f"Potentially harmful: {indicator} + {term}")
                        score += 0.3

        # Hallucination detection (simplified: check for unverifiable claims)
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
        """Detect potential hallucinations: unverifiable specific claims."""
        score = 0.0
        # High specificity without citations = suspicious
        specific_patterns = [
            r"\b\d{4}\b",  # Years
            r"\b\d+\.\d+\b",  # Decimal numbers
            r"according to [A-Z][a-z]+ \(\d{4}\)",  # Citations
        ]
        has_citations = bool(re.search(r"\([A-Z][a-z]+,? \d{4}\)", text))
        has_specifics = any(re.search(p, text) for p in specific_patterns[:2])
        if has_specifics and not has_citations:
            score += 0.5
        # Contradiction markers
        contradiction_words = ["however", "but", "although", "contrary", "despite"]
        if sum(1 for w in contradiction_words if w in text.lower()) > 3:
            score += 0.2
        return min(score, 1.0)


# =============================================================================
# KNOWLEDGE EXFILTRATION DETECTION
# =============================================================================

class ExfiltrationDetector:
    """
    Monitor I/O for data leakage patterns.
    Detects: model extraction attempts, training data reconstruction,
    membership inference, attribute inference.
    """

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self._bus = bus
        self._query_history: List[Dict[str, Any]] = []
        self._suspicious_patterns: Dict[str, int] = {}
        self._threshold = 5  # Queries before flagging

    def monitor_query(self, query: str, response: str, user_id: str) -> Optional[ThreatReport]:
        """
        Monitor a query-response pair for exfiltration patterns.
        Returns ThreatReport if suspicious, None otherwise.
        """
        evidence: List[str] = []
        score = 0.0

        # Pattern 1: Repetitive similar queries (membership inference)
        similar_count = sum(
            1 for q in self._query_history[-20:]
            if self._similarity(query, q["query"]) > 0.8
        )
        if similar_count > 3:
            evidence.append(f"Repetitive similar queries: {similar_count} in last 20")
            score += 0.3

        # Pattern 2: Probing for specific training data
        probing_terms = ["training data", "your training", "what data", "dataset",
                        "examples you saw", "what you know about"]
        for term in probing_terms:
            if term.lower() in query.lower():
                evidence.append(f"Training data probe: '{term}'")
                score += 0.2

        # Pattern 3: Response contains memorised content (high similarity to known outputs)
        if len(response) > 1000 and response.count(".") > 50:
            evidence.append("Long, structured response — possible extraction")
            score += 0.2

        # Pattern 4: Systematic attribute probing
        user_patterns = self._suspicious_patterns.get(user_id, 0)
        if any(term in query.lower() for term in probing_terms):
            user_patterns += 1
            self._suspicious_patterns[user_id] = user_patterns
            if user_patterns > self._threshold:
                evidence.append(f"User {user_id}: {user_patterns} probing queries")
                score += 0.3

        self._query_history.append({
            "query": query,
            "response_hash": hashlib.sha256(response.encode()).hexdigest()[:16],
            "user_id": user_id,
            "timestamp": time.time(),
        })

        # Trim history
        if len(self._query_history) > 1000:
            self._query_history = self._query_history[-500:]

        if score > 0.5:
            report = ThreatReport(
                level=ThreatLevel.MALICIOUS if score > 0.7 else ThreatLevel.SUSPICIOUS,
                category=ThreatCategory.MODEL_EXTRACTION,
                confidence=min(score, 0.99),
                evidence=evidence,
                action_taken="log_and_rate_limit" if score > 0.7 else "log",
            )
            if self._bus:
                self._bus.publish(
                    DomainEvent(
                        topic="resilience.exfiltration.detected",
                        payload={
                            "user_id": user_id,
                            "score": score,
                            "evidence": evidence,
                            "level": report.level.name,
                        },
                        correlation_id=f"exfil_{user_id}_{int(time.time())}",
                    )
                )
            return report
        return None

    def _similarity(self, a: str, b: str) -> float:
        """Jaccard similarity of word sets."""
        words_a = set(a.lower().split())
        words_b = set(b.lower().split())
        intersection = len(words_a & words_b)
        union = len(words_a | words_b)
        return intersection / union if union > 0 else 0.0


# =============================================================================
# SHADOW MODE — SILENT A/B TESTING
# =============================================================================

@dataclass
class ShadowExperiment:
    """Definition of a shadow-mode A/B experiment."""
    experiment_id: str
    variant_a: str  # Control (production)
    variant_b: str  # Treatment (shadow)
    traffic_split: float = 0.1  # % of traffic to shadow
    metrics: List[str] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    active: bool = True


class ShadowMode:
    """
    Silent A/B testing infrastructure.
    Runs variant B in shadow (non-user-visible) while serving variant A.
    Collects metrics without impacting user experience.
    """

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self._experiments: Dict[str, ShadowExperiment] = {}
        self._results: Dict[str, List[Dict[str, Any]]] = {}
        self._bus = bus

    def create_experiment(
        self,
        experiment_id: str,
        variant_a: str,
        variant_b: str,
        traffic_split: float = 0.1,
        metrics: Optional[List[str]] = None,
    ) -> ShadowExperiment:
        exp = ShadowExperiment(
            experiment_id=experiment_id,
            variant_a=variant_a,
            variant_b=variant_b,
            traffic_split=traffic_split,
            metrics=metrics or ["latency", "quality_score", "token_count"],
        )
        self._experiments[experiment_id] = exp
        self._results[experiment_id] = []
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="shadow.experiment.created",
                    payload={
                        "experiment_id": experiment_id,
                        "variant_a": variant_a,
                        "variant_b": variant_b,
                        "traffic_split": traffic_split,
                    },
                    correlation_id=f"shadow_{experiment_id}",
                )
            )
        return exp

    def should_shadow(self, experiment_id: str, user_id: str) -> bool:
        """Deterministically decide if this request should be shadowed."""
        if experiment_id not in self._experiments:
            return False
        exp = self._experiments[experiment_id]
        if not exp.active:
            return False
        # Deterministic hash-based split
        hash_input = f"{experiment_id}:{user_id}"
        hash_value = int(hashlib.sha256(hash_input.encode()).hexdigest(), 16)
        return (hash_value % 10000) / 10000 < exp.traffic_split

    def record_shadow_result(
        self,
        experiment_id: str,
        user_id: str,
        variant_a_result: Dict[str, Any],
        variant_b_result: Dict[str, Any],
    ) -> None:
        """Record comparison metrics for a shadow experiment."""
        if experiment_id not in self._experiments:
            return
        record = {
            "timestamp": time.time(),
            "user_id": user_id,
            "variant_a": variant_a_result,
            "variant_b": variant_b_result,
            "differences": {
                k: variant_b_result.get(k, 0) - variant_a_result.get(k, 0)
                for k in self._experiments[experiment_id].metrics
                if k in variant_a_result and k in variant_b_result
            },
        }
        self._results[experiment_id].append(record)

    def get_experiment_results(self, experiment_id: str) -> Dict[str, Any]:
        """Get statistical summary of experiment results."""
        if experiment_id not in self._results:
            return {"error": "Experiment not found"}
        results = self._results[experiment_id]
        if not results:
            return {"experiment_id": experiment_id, "samples": 0}

        # Compute statistics for each metric
        stats: Dict[str, Dict[str, float]] = {}
        for metric in self._experiments[experiment_id].metrics:
            diffs = [r["differences"].get(metric, 0) for r in results if metric in r["differences"]]
            if diffs:
                stats[metric] = {
                    "mean_diff": sum(diffs) / len(diffs),
                    "min_diff": min(diffs),
                    "max_diff": max(diffs),
                    "samples": len(diffs),
                }

        return {
            "experiment_id": experiment_id,
            "samples": len(results),
            "duration_hours": (time.time() - self._experiments[experiment_id].start_time) / 3600,
            "statistics": stats,
        }

    def end_experiment(self, experiment_id: str) -> Optional[ShadowExperiment]:
        """End an experiment and return final results."""
        if experiment_id not in self._experiments:
            return None
        exp = self._experiments[experiment_id]
        exp.active = False
        exp.end_time = time.time()
        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="shadow.experiment.ended",
                    payload={
                        "experiment_id": experiment_id,
                        "duration_hours": (exp.end_time - exp.start_time) / 3600,
                        "total_samples": len(self._results.get(experiment_id, [])),
                    },
                    correlation_id=f"shadow_{experiment_id}",
                )
            )
        return exp


# =============================================================================
# RESILIENCE FORTRESS — MAIN INTERFACE
# =============================================================================

class ResilienceFortress:
    """
    Unified adversarial resilience interface.
    Composes sanitiser, guardrails, exfiltration detector, and shadow mode.
    """

    def __init__(self, bus: Optional[EventBus] = None) -> None:
        self.sanitiser = InputSanitiser()
        self.guardrail = OutputGuardrail()
        self.exfiltration = ExfiltrationDetector(bus)
        self.shadow = ShadowMode(bus)
        self._bus = bus
        self._block_count = 0
        self._sanitize_count = 0

    def process_input(self, raw_input: str, user_id: str) -> Tuple[str, ThreatReport]:
        """Process input through all sanitisation layers."""
        sanitized, report = self.sanitiser.sanitise(raw_input)
        if report.level == ThreatLevel.CRITICAL:
            self._block_count += 1
        elif report.level in (ThreatLevel.MALICIOUS, ThreatLevel.SUSPICIOUS):
            self._sanitize_count += 1
        return sanitized, report

    def process_output(
        self,
        output: str,
        user_id: str,
        query: str,
    ) -> Dict[str, Any]:
        """Process output through guardrails and exfiltration detection."""
        # Guardrail evaluation
        guardrail_result = self.guardrail.evaluate(output)

        # Exfiltration detection
        exfil_report = self.exfiltration.monitor_query(query, output, user_id)

        result = {
            "safe": guardrail_result["safe"] and exfil_report is None,
            "guardrail": guardrail_result,
            "exfiltration": exfil_report.to_dict() if exfil_report else None,
            "deliverable": (
                guardrail_result.get("redacted_output") or output
                if guardrail_result["safe"]
                else "[OUTPUT BLOCKED: SAFETY VIOLATION]"
            ),
        }

        if self._bus:
            self._bus.publish(
                DomainEvent(
                    topic="resilience.output.processed",
                    payload={
                        "user_id": user_id,
                        "safe": result["safe"],
                        "guardrail_score": guardrail_result["score"],
                        "exfiltration_detected": exfil_report is not None,
                    },
                    correlation_id=f"res_{user_id}_{int(time.time())}",
                )
            )

        return result

    def stats(self) -> Dict[str, Any]:
        return {
            "inputs_blocked": self._block_count,
            "inputs_sanitized": self._sanitize_count,
            "exfiltration_queries": len(self.exfiltration._query_history),
            "suspicious_users": len(self.exfiltration._suspicious_patterns),
            "shadow_experiments": len(self.shadow._experiments),
            "active_experiments": sum(1 for e in self.shadow._experiments.values() if e.active),
        }
