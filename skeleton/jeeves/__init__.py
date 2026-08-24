"""Jeeves package — the AI tutor brain."""

from .cocoding import CoCodingOrchestrator, CoCodingSession, SkillLevel, Stage
from .knowledge import Concept, ConceptEdge, ConceptError, EdgeType, KnowledgeGraph
from .socratic import Belief, Dialogue, SocraticEngine, SocraticMove, Turn

__all__ = [
    "CoCodingOrchestrator", "CoCodingSession", "SkillLevel", "Stage",
    "KnowledgeGraph", "Concept", "ConceptEdge", "ConceptError", "EdgeType",
    "SocraticEngine", "SocraticMove", "Belief", "Dialogue", "Turn",
]
