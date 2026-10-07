#!/usr/bin/env python3
"""
Exocortex ↔ Knowledge Nexus Deep Integration
"""

from exocortex.exocortex_layers import exocortex
from engines.knowledge_nexus_jury_engine import knowledge_nexus_jury
from engines.wiki_memory_engine import wiki_memory_engine
from engines.aaahrage_hybrid_rag_engine import aaahrage_engine

class ExocortexNexusBridge:
    def __init__(self):
        self.exocortex = exocortex
        self.jury = knowledge_nexus_jury
        self.wiki = wiki_memory_engine
        self.rag = aaahrage_engine

    def process_and_persist_learning(self, experience: str, outcome: str):
        """Process experience in Exocortex and route valuable learning to Nexus."""
        # Store in Exocortex
        self.exocortex.memory.store("recent_experience", experience)
        self.exocortex.reflection.reflect(experience, outcome)
        
        # If high value, prepare for permanent storage
        if "learned" in outcome.lower() or "improved" in outcome.lower() or len(experience) > 100:
            content = f"Experience: {experience}\nOutcome: {outcome}"
            package = {
                "content_id": f"exo_learn_{int(time.time())}",
                "content": content
            }
            
            decision = self.jury.evaluate_content(package["content_id"], content)
            
            if decision.final_vote.value == "accept":
                self.wiki.build_wiki(package["content_id"], content, sources=["Exocortex"])
                print("[Exocortex-Nexus] Valuable learning permanently stored via Knowledge Nexus.")

# Global bridge
exocortex_nexus_bridge = ExocortexNexusBridge()