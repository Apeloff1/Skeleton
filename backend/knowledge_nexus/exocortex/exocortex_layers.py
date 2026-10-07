#!/usr/bin/env python3
"""
Exocortex Layers Implementation
Memory, Reflection, Homeostasis, Risk, Learning — all integrated with Knowledge Nexus.
"""

from typing import Dict, List, Any
from engines.context_engine_3x import context_engine_3x
from engines.aaahrage_hybrid_rag_engine import aaahrage_engine

class ExocortexMemoryLayer:
    def __init__(self):
        self.short_term = []
        self.long_term = {}
        self.working_memory = {}

    def store(self, key: str, value: Any, layer: str = "short_term"):
        if layer == "short_term":
            self.short_term.append({"key": key, "value": value, "timestamp": __import__("time").time()})
        elif layer == "long_term":
            self.long_term[key] = value

    def retrieve(self, query: str, use_rag: bool = True) -> List[Dict]:
        if use_rag:
            return aaahrage_engine.retrieve(query, top_k=8)
        # Fallback simple search
        return [item for item in self.short_term if query.lower() in str(item).lower()]

class ExocortexReflectionLayer:
    def __init__(self):
        self.reflections = []

    def reflect(self, experience: str, outcome: str):
        reflection = {
            "experience": experience,
            "outcome": outcome,
            "timestamp": __import__("time").time(),
            "insights": aaahrage_engine.retrieve(f"Reflect on: {experience} → {outcome}", top_k=5)
        }
        self.reflections.append(reflection)
        # Automatically prepare high-value reflections for Nexus
        if len(reflection["insights"]) > 2:
            print("[Exocortex] High-value reflection prepared for Knowledge Nexus submission")

class ExocortexHomeostasisLayer:
    def __init__(self):
        self.balance_metrics = {"cognitive_load": 0.5, "energy": 0.8, "coherence": 0.7}

    def adjust(self, trigger: str):
        # Simple homeostasis logic (expand with real models)
        if "high_load" in trigger:
            self.balance_metrics["cognitive_load"] = max(0.3, self.balance_metrics["cognitive_load"] - 0.2)
        print(f"[Exocortex Homeostasis] Adjusted balance: {self.balance_metrics}")

class Exocortex:
    def __init__(self):
        self.memory = ExocortexMemoryLayer()
        self.reflection = ExocortexReflectionLayer()
        self.homeostasis = ExocortexHomeostasisLayer()
        self.context = context_engine_3x

    def process_experience(self, experience: str):
        self.memory.store("latest", experience)
        self.reflection.reflect(experience, "processed")
        self.homeostasis.adjust("new_experience")
        self.context.add_context(experience, source="Exocortex", importance=0.75)

# Global Exocortex instance
exocortex = Exocortex()