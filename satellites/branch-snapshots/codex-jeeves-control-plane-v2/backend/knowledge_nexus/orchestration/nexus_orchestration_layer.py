#!/usr/bin/env python3
"""
Nexus Orchestration Layer
Coordinates Jeeves, Exocortex, Librarian Agent, and the Multi-Agent Knowledge Nexus.
"""

import time
from engines.context_engine_3x import context_engine_3x
from engines.aaahrage_hybrid_rag_engine import aaahrage_engine
from engines.knowledge_nexus_jury_engine import knowledge_nexus_jury
from agents.librarian_agent_implementation import librarian_agent
from engines.wiki_memory_engine import wiki_memory_engine

class NexusOrchestrator:
    def __init__(self):
        self.context = context_engine_3x
        self.rag = aaahrage_engine
        self.jury = knowledge_nexus_jury
        self.librarian = librarian_agent
        self.wiki = wiki_memory_engine

    def process_important_event(self, event_description: str, source: str = "system"):
        """Main entry point for important events that may need permanent memory."""
        # 1. Add to high-quality context
        self.context.add_context(event_description, source=source, importance=0.8)
        
        # 2. Retrieve relevant context using AAAHRAG + Hybrid RAG
        relevant = self.rag.retrieve(event_description, top_k=8)
        
        # 3. Prepare package via Librarian
        package = self.librarian.prepare_jury_package(
            content_id=f"event_{int(time.time())}",
            content=event_description
        )
        
        # 4. Submit to Jury for evaluation
        decision = self.jury.evaluate_content(
            content_id=package["content_id"],
            content=event_description,
            context={"supporting_evidence": package["supporting_evidence"]}
        )
        
        # 5. If accepted, write to Wiki Memory
        if decision.final_vote.value == "accept":
            self.wiki.build_wiki(
                content_id=package["content_id"],
                content=event_description,
                sources=[source]
            )
            print(f"[NexusOrchestrator] Content permanently stored in Wiki Memory: {package['content_id']}")
        
        return decision

# Global orchestrator
nexus_orchestrator = NexusOrchestrator()