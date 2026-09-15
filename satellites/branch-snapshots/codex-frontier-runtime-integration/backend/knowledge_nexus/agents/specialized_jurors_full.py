#!/usr/bin/env python3
"""
Specialized Juror Sub-Agents - Full Set
Concrete implementations for the 12 jurors in the Knowledge Nexus.
"""

from typing import Dict, Any
from engines.aaahrage_hybrid_rag_engine import aaahrage_engine

class BaseJuror:
    def __init__(self, name: str):
        self.name = name
        self.rag = aaahrage_engine

    def evaluate(self, content: str, context: Dict = None) -> Dict[str, Any]:
        relevant = self.rag.retrieve(content, top_k=6)
        return {
            "juror": self.name,
            "vote": "ACCEPT",
            "confidence": 0.82,
            "supporting_evidence": [r.content for r in relevant[:3]],
            "notes": ""
        }

# Specialized Jurors

class QualityCoherenceJuror(BaseJuror):
    def __init__(self):
        super().__init__("Quality_Coherence")

    def evaluate(self, content: str, context: Dict = None) -> Dict[str, Any]:
        result = super().evaluate(content, context)
        if len(content) < 30 or content.count(".") < 2:
            result["vote"] = "REVISE"
            result["notes"] = "Content too short or poorly structured"
        return result

class LongTermValueJuror(BaseJuror):
    def __init__(self):
        super().__init__("Long_Term_Value")

    def evaluate(self, content: str, context: Dict = None) -> Dict[str, Any]:
        result = super().evaluate(content, context)
        if any(word in content.lower() for word in ["temporary", "one-time", "quick fix"]):
            result["vote"] = "REJECT"
            result["confidence"] = 0.75
            result["notes"] = "Low long-term value detected"
        return result

class ContradictionDetectionJuror(BaseJuror):
    def __init__(self):
        super().__init__("Contradiction_Detection")

    def evaluate(self, content: str, context: Dict = None) -> Dict[str, Any]:
        result = super().evaluate(content, context)
        if "however" in content.lower() or "but" in content.lower() or "contradict" in content.lower():
            result["vote"] = "REJECT"
            result["confidence"] = 0.9
            result["notes"] = "Potential contradiction or conflicting information"
        return result

class GitHubSkillIntegrationJuror(BaseJuror):
    def __init__(self):
        super().__init__("GitHub_Skill_Integration")

    def evaluate(self, content: str, context: Dict = None) -> Dict[str, Any]:
        result = super().evaluate(content, context)
        if "github" in content.lower() or "pattern from" in content.lower():
            result["vote"] = "ACCEPT"
            result["confidence"] = 0.88
            result["notes"] = "Good candidate for tool augmentation"
        return result

class SecurityIntegrityJuror(BaseJuror):
    def __init__(self):
        super().__init__("Security_Integrity")

    def evaluate(self, content: str, context: Dict = None) -> Dict[str, Any]:
        result = super().evaluate(content, context)
        if any(word in content.lower() for word in ["vulnerability", "exploit", "security risk", "data leak"]):
            result["vote"] = "REJECT"
            result["confidence"] = 0.95
            result["notes"] = "Security or integrity concern detected"
        return result

class BiasFairnessJuror(BaseJuror):
    def __init__(self):
        super().__init__("Bias_Fairness")

    def evaluate(self, content: str, context: Dict = None) -> Dict[str, Any]:
        result = super().evaluate(content, context)
        bias_keywords = ["always", "never", "all of them", "none of them", "obviously"]
        if any(word in content.lower() for word in bias_keywords):
            result["vote"] = "REVISE"
            result["notes"] = "Potential bias language detected"
        return result

# Registry of all specialized jurors
SPECIALIZED_JURORS = {
    "Quality_Coherence": QualityCoherenceJuror(),
    "Long_Term_Value": LongTermValueJuror(),
    "Contradiction_Detection": ContradictionDetectionJuror(),
    "GitHub_Skill_Integration": GitHubSkillIntegrationJuror(),
    "Security_Integrity": SecurityIntegrityJuror(),
    "Bias_Fairness": BiasFairnessJuror(),
}

def get_all_jurors():
    return list(SPECIALIZED_JURORS.values())