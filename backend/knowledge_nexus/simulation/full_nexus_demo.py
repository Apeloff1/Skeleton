#!/usr/bin/env python3
"""
Full Knowledge Nexus Demo / Simulation
Demonstrates the integrated flow of Context Engine 3×, AAAHRAG + Hybrid RAG,
Librarian Agent, Multi-Agent Jury, Wiki Memory, and supporting systems.
"""

import time
from engines.context_engine_3x import context_engine_3x
from engines.aaahrage_hybrid_rag_engine import aaahrage_engine
from agents.librarian_agent_implementation import librarian_agent
from engines.knowledge_nexus_jury_engine import knowledge_nexus_jury
from engines.wiki_memory_engine import wiki_memory_engine
from agents.proof_reader_grader_implementation import proof_reader, grader
from engines.chronoback_blockchain_implementation import chronoback, blockchain
from exocortex.exocortex_layers import exocortex
from jeeves.jeeves_core_orchestration import jeeves

def run_full_demo():
    print("=" * 60)
    print("FULL KNOWLEDGE NEXUS SYSTEM DEMO")
    print("=" * 60)

    # 1. Context Engine 3× receives new experience
    print("\n[1] Context Engine 3× processing new experience...")
    context_engine_3x.add_context(
        "Learned that combining AAAHRAG with Hybrid RAG dramatically improves retrieval quality in complex domains.",
        source="Exocortex_Reflection",
        importance=0.9
    )
    print("   → Context added and noise-filtered.")

    # 2. Exocortex processes and reflects
    print("\n[2] Exocortex processing experience...")
    exocortex.process_experience(
        "Combined retrieval methods in Knowledge Nexus",
        "Significant improvement in accuracy and speed"
    )

    # 3. Jeeves handles strategic task
    print("\n[3] Jeeves processing strategic task...")
    result = jeeves.process_task(
        "Permanently store the lesson about hybrid retrieval in the Knowledge Nexus",
        priority=0.85
    )
    print(f"   → Jeeves result: {result['status']}")

    # 4. Librarian prepares high-quality package
    print("\n[4] Librarian Agent preparing Jury package...")
    package = librarian_agent.prepare_jury_package(
        "demo_lesson_001",
        "Hybrid RAG + AAAHRAG significantly improves retrieval in the Knowledge Nexus."
    )
    print(f"   → Package prepared with {len(package.get('supporting_evidence', []))} supporting items")

    # 5. Proof Reader + Grader review
    print("\n[5] Proof Reader and Grader reviewing content...")
    proof_result = proof_reader.review(package["original_content"])
    grade_result = grader.grade(package["original_content"])
    print(f"   → Proof issues: {proof_result['issues_found']}")
    print(f"   → Grade: Importance={grade_result['importance']}, Confidence={grade_result['confidence']}, Risk={grade_result['risk']}")

    # 6. Multi-Agent Jury evaluates
    print("\n[6] Multi-Agent Knowledge Nexus Jury evaluating...")
    decision = knowledge_nexus_jury.evaluate_content(
        content_id=package["content_id"],
        content=package["original_content"],
        require_supermajority=True
    )
    print(f"   → Final Decision: {decision.final_vote.value} (Confidence: {decision.confidence})")
    print(f"   → Rationale: {decision.rationale}")

    # 7. If accepted, store in Wiki Memory + create snapshot
    if decision.final_vote.value == "accept":
        print("\n[7] Content approved. Storing in Wiki Memory...")
        wiki_memory_engine.build_wiki(
            content_id=package["content_id"],
            content=package["original_content"],
            sources=["Jeeves", "Exocortex", "Librarian"]
        )
        chronoback.create_snapshot({"wiki_entry": package["content_id"]})
        blockchain.record_change("knowledge_approved", package["content_id"], {"jury_decision": decision.final_vote.value})
        print("   → Successfully stored in Wiki Memory with backup and provenance.")

    # 8. Final status
    print("\n[8] Final System Status:")
    print(f"   - Active Context items: {len(context_engine_3x.active_context)}")
    print(f"   - Wiki Memory entries: {len(wiki_memory_engine.wiki_entries)}")
    print(f"   - Jury decisions logged: {len(knowledge_nexus_jury.decisions_log)}")
    print(f"   - ChronoBack snapshots: {len(chronoback.snapshots)}")
    print(f"   - Blockchain blocks: {len(blockchain.chain)}")

    print("\n" + "=" * 60)
    print("DEMO COMPLETED SUCCESSFULLY")
    print("=" * 60)

if __name__ == "__main__":
    run_full_demo()