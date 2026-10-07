#!/usr/bin/env python3
"""
Knowledge Nexus Testing & Simulation Harness
Basic framework for testing the Multi-Agent Knowledge Nexus and related systems.
"""

import time
from engines.knowledge_nexus_jury_engine import knowledge_nexus_jury
from engines.wiki_memory_engine import wiki_memory_engine
from agents.librarian_agent_implementation import librarian_agent
from engines.aaahrage_hybrid_rag_engine import aaahrage_engine

def test_jury_evaluation():
    print("\n=== Testing Jury Evaluation ===")
    content = "This is a high-value reflection about using GitHub patterns to improve AI behavior design."
    decision = knowledge_nexus_jury.evaluate_content(
        content_id="test_001",
        content=content,
        require_supermajority=False
    )
    print(f"Decision: {decision.final_vote.value} | Confidence: {decision.confidence}")
    print(f"Rationale: {decision.rationale}")
    return decision

def test_wiki_memory():
    print("\n=== Testing Wiki Memory ===")
    entry = wiki_memory_engine.build_wiki(
        content_id="test_wiki_001",
        content="Permanent knowledge about Context Engine 3× and AAAHRAG integration.",
        sources=["Exocortex", "Jeeves"]
    )
    print(f"Wiki entry created: {entry.id}")
    return entry

def test_librarian_extraction():
    print("\n=== Testing Librarian Extraction ===")
    results = librarian_agent.extract_from_bookshelf(
        query="Context Engine and Knowledge Nexus integration",
        db_styles=["wiki_knowledge_base", "analytics_metrics"],
        top_k=5
    )
    print(f"Librarian retrieved {len(results)} items")
    return results

def test_full_flow():
    print("\n=== Full Nexus Flow Test ===")
    content = "Important learning: Using Hybrid RAG + AAAHRAG significantly improves retrieval quality in the Knowledge Nexus."
    
    # Step 1: Librarian prepares package
    package = librarian_agent.prepare_jury_package("flow_test_001", content)
    
    # Step 2: Jury evaluates
    decision = knowledge_nexus_jury.evaluate_content(package["content_id"], content)
    
    # Step 3: If accepted, store in Wiki Memory
    if decision.final_vote.value == "accept":
        wiki_memory_engine.build_wiki(package["content_id"], content, sources=["Test Harness"])
        print("Content successfully passed through Nexus and stored in Wiki Memory.")
    else:
        print(f"Content rejected by Jury: {decision.rationale}")

if __name__ == "__main__":
    test_jury_evaluation()
    test_wiki_memory()
    test_librarian_extraction()
    test_full_flow()
    print("\n=== All basic tests completed ===")