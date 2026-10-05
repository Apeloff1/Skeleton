"""Threat classification types — split from the resilience monolith (v16.2)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional


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
    confidence: float
    evidence: List[str]
    sanitized_input: Optional[str] = None
    action_taken: str = "none"
    timestamp: float = field(default_factory=time.time)
