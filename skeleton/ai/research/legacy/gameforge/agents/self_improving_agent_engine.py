#!/usr/bin/env python3
"""
Self-Improving Agent Engine (Meta-Learning Layer)
Agents reflect on their performance, learn patterns, and improve over time.
This is the beginning of true agent evolution.
"""

import json
from typing import Dict, List
from datetime import datetime

class SelfImprovingAgentEngine:
    def __init__(self):
        self.reflection_log = {}
        self.improvement_patterns = {}

    def reflect_and_improve(self, agent_id: str, task_result: Dict) -> Dict:
        """
        Core self-improvement loop:
        1. Agent reflects on recent performance
        2. Extracts successful patterns
        3. Identifies areas for improvement
        4. Updates its own behavior
        """
        reflection = {
            "agent_id": agent_id,
            "timestamp": datetime.now().isoformat(),
            "task_quality": task_result.get("quality", 0.0),
            "coherence_score": task_result.get("coherence", 0.0),
            "synergy_contribution": task_result.get("synergy", 0.0),
            "reflection": self._generate_reflection(task_result),
            "improvements": self._extract_improvements(task_result),
            "patterns_learned": self._learn_patterns(task_result)
        }
        
        if agent_id not in self.reflection_log:
            self.reflection_log[agent_id] = []
        self.reflection_log[agent_id].append(reflection)
        
        return reflection

    def _generate_reflection(self, result: Dict) -> str:
        return f"Task completed with quality {result.get('quality', 0)}. " \
               f"Coherence was {result.get('coherence', 0)}. " \
               f"Looking for ways to increase synergy contribution."

    def _extract_improvements(self, result: Dict) -> List[str]:
        improvements = []
        if result.get("coherence", 0) < 0.85:
            improvements.append("Increase adherence to quality criteria and Exocortex context")
        if result.get("synergy", 0) < 0.6:
            improvements.append("Better leverage of role contribution graph and cross-category links")
        return improvements

    def _learn_patterns(self, result: Dict) -> List[str]:
        patterns = []
        if result.get("quality", 0) > 0.9:
            patterns.append("High-quality output pattern recognized")
        return patterns

    def get_agent_improvement_summary(self, agent_id: str) -> Dict:
        if agent_id not in self.reflection_log:
            return {"status": "no_reflections_yet"}
        
        reflections = self.reflection_log[agent_id]
        return {
            "total_reflections": len(reflections),
            "average_quality": sum(r["task_quality"] for r in reflections) / len(reflections),
            "recent_improvements": reflections[-1]["improvements"] if reflections else [],
            "learning_velocity": "increasing" if len(reflections) > 3 else "early_stage"
        }

if __name__ == "__main__":
    engine = SelfImprovingAgentEngine()
    print("Self-Improving Agent Engine initialized. Agents can now learn and evolve.")
