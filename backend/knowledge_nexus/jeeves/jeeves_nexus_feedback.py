from typing import Dict, List, Any, Dict, List, Optional
#!/usr/bin/env python3
"""
Jeeves Nexus Feedback Integration
Enhanced decision-making with direct feedback from the Knowledge Nexus.
"""

from jeeves.jeeves_core_orchestration import jeeves
from engines.knowledge_nexus_jury_engine import knowledge_nexus_jury
from engines.wiki_memory_engine import wiki_memory_engine
from engines.aaahrage_hybrid_rag_engine import aaahrage_engine

class JeevesWithNexusFeedback:
    def __init__(self):
        self.jeeves = jeeves
        self.jury = knowledge_nexus_jury
        self.wiki = wiki_memory_engine
        self.rag = aaahrage_engine

    def make_strategic_decision(self, situation: str, options: List[str]) -> Dict:
        """Make a decision with full Nexus awareness."""
        # Retrieve relevant permanent knowledge
        relevant = self.rag.retrieve(situation, top_k=10)
        
        # Check if similar past decisions exist in Wiki Memory
        past_decisions = self.wiki.get_wiki_context(situation, top_k=5)
        
        # Prepare for Nexus if high stakes
        if len(options) > 2 or "permanent" in situation.lower():
            package = self.jeeves.librarian.prepare_jury_package(
                content_id=f"strategic_{int(time.time())}",
                content=f"Situation: {situation}\nOptions: {options}"
            )
            decision = self.jury.evaluate_content(package["content_id"], package["original_content"])
            
            if decision.final_vote.value == "accept":
                self.wiki.build_wiki(package["content_id"], package["original_content"], sources=["Jeeves_Strategic"])
        
        return {
            "situation": situation,
            "relevant_permanent_knowledge": [r.content for r in relevant[:5]],
            "past_wiki_entries": len(past_decisions),
            "nexus_consulted": True
        }

# Global enhanced Jeeves
jeeves_nexus = JeevesWithNexusFeedback()