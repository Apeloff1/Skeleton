#!/usr/bin/env python3
"""
Jeeves Core Orchestration Loop
Main decision and delegation engine with deep integration into the Knowledge Nexus.
"""

import time
from typing import Dict, Any, List
from engines.context_engine_3x import context_engine_3x
from engines.aaahrage_hybrid_rag_engine import aaahrage_engine
from engines.knowledge_nexus_jury_engine import knowledge_nexus_jury
from agents.librarian_agent_implementation import librarian_agent
from engines.wiki_memory_engine import wiki_memory_engine
from engines.nexus_orchestration_layer import nexus_orchestrator

class JeevesCore:
    def __init__(self):
        self.name = "Jeeves"
        self.context = context_engine_3x
        self.rag = aaahrage_engine
        self.jury = knowledge_nexus_jury
        self.librarian = librarian_agent
        self.wiki = wiki_memory_engine
        self.orchestrator = nexus_orchestrator
        self.decision_history = []

    def process_task(self, task_description: str, priority: float = 0.7) -> Dict[str, Any]:
        """
        Main entry point for Jeeves when handling tasks or important events.
        """
        print(f"\n[Jeeves] Processing task: {task_description}")

        # 1. Update context with high importance
        self.context.add_context(task_description, source="Jeeves", importance=priority)

        # 2. Retrieve relevant knowledge using AAAHRAG + Hybrid RAG
        relevant_knowledge = self.rag.retrieve(task_description, top_k=12, use_agentic=True, use_hybrid=True)

        # 3. If this is high-impact, prepare and delegate to Knowledge Nexus
        if priority > 0.65 or "permanent" in task_description.lower() or "learn" in task_description.lower():
            package = self.librarian.prepare_jury_package(
                content_id=f"jeeves_task_{int(time.time())}",
                content=task_description
            )
            
            decision = self.jury.evaluate_content(
                content_id=package["content_id"],
                content=task_description,
                context={"supporting_knowledge": [k.content for k in relevant_knowledge]}
            )
            
            self.decision_history.append(decision)
            
            if decision.final_vote.value == "accept":
                self.wiki.build_wiki(
                    content_id=package["content_id"],
                    content=task_description,
                    sources=["Jeeves", "Knowledge_Nexus"]
                )
                print(f"[Jeeves] → Content approved and stored in Wiki Memory via Nexus")

            return {
                "status": "delegated_to_nexus",
                "decision": decision,
                "relevant_knowledge_count": len(relevant_knowledge)
            }

        # Normal task handling
        return {
            "status": "handled_directly",
            "relevant_knowledge": [k.content for k in relevant_knowledge[:5]]
        }

    def get_status(self) -> Dict:
        return {
            "active_context_size": len(self.context.active_context),
            "decisions_made": len(self.decision_history),
            "wiki_entries": len(self.wiki.wiki_entries)
        }

# Global Jeeves instance
jeeves = JeevesCore()