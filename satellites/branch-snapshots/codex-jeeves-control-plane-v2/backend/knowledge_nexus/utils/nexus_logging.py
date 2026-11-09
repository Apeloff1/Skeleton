#!/usr/bin/env python3
"""
Nexus Logging & Observability Helper
Simple structured logging for the Knowledge Nexus system.
"""

import logging
import json
from datetime import datetime

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s'
)

logger = logging.getLogger("KnowledgeNexus")

def log_nexus_event(event_type: str, details: dict):
    """Log structured events from the Knowledge Nexus."""
    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": event_type,
        "details": details
    }
    logger.info(json.dumps(log_entry))

def log_jury_decision(decision):
    """Log a jury decision."""
    log_nexus_event("jury_decision", {
        "content_id": decision.content_id,
        "final_vote": decision.final_vote.value,
        "confidence": decision.confidence,
        "rationale": decision.rationale
    })

def log_wiki_update(content_id: str, action: str):
    """Log Wiki Memory updates."""
    log_nexus_event("wiki_update", {
        "content_id": content_id,
        "action": action
    })

# Example usage
if __name__ == "__main__":
    log_nexus_event("system_startup", {"version": "Knowledge_Nexus_v1"})
    log_wiki_update("demo_001", "created")