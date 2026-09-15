#!/usr/bin/env python3
"""
Enhanced Nexus Testing Harness
More comprehensive testing scenarios for the Knowledge Nexus system.
"""

from testing.nexus_testing_harness import (
    test_jury_evaluation, 
    test_wiki_memory, 
    test_librarian_extraction, 
    test_full_flow
)
from engines.knowledge_nexus_jury_engine import knowledge_nexus_jury
from agents.specialized_jurors_full import SPECIALIZED_JURORS
from databases.concrete_databases import blockchain_db, logbook_db
from engines.chronoback_blockchain_implementation import chronoback, blockchain

def test_specialized_jurors():
    print("\n=== Testing Specialized Jurors ===")
    test_content = "Using GitHub patterns improved our AI behavior significantly, but there might be some edge cases with bias in the training data."
    
    for name, juror in SPECIALIZED_JURORS.items():
        result = juror.evaluate(test_content)
        print(f"{name}: {result['vote']} (confidence: {result['confidence']})")

def test_database_storage():
    print("\n=== Testing Concrete Databases ===")
    
    # Blockchain
    blockchain_db.store("tx_001", {"action": "approved_knowledge", "content_id": "wiki_123"})
    print(f"Blockchain chain length: {len(blockchain_db.chain)}")
    
    # Logbook
    logbook_db.store("log_001", "Important system event occurred", {"severity": "high"})
    recent = logbook_db.get_recent_logs(5)
    print(f"Recent logbook entries: {len(recent)}")

def test_integrity_systems():
    print("\n=== Testing ChronoBack + Blockchain ===")
    data = {"important": "knowledge state"}
    
    chronoback.create_snapshot(data)
    is_valid = chronoback.verify_integrity(data)
    print(f"Data integrity check: {'PASS' if is_valid else 'FAIL'}")
    
    blockchain.record_change("knowledge_approved", "wiki_123", {"juror_consensus": True})

def run_full_test_suite():
    print("\n" + "="*50)
    print("FULL KNOWLEDGE NEXUS TEST SUITE")
    print("="*50)
    
    test_jury_evaluation()
    test_wiki_memory()
    test_librarian_extraction()
    test_full_flow()
    test_specialized_jurors()
    test_database_storage()
    test_integrity_systems()
    
    print("\n" + "="*50)
    print("ALL TESTS COMPLETED")
    print("="*50)

if __name__ == "__main__":
    run_full_test_suite()