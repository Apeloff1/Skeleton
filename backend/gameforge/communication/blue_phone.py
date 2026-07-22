#!/usr/bin/env python3
"""
Jeeves Blue Phone - Queued Communication System
Inspired by earlier Jeeves design. Allows agents to make queued calls to Jeeves/Exocortex
with priority, context, and response handling. Max queue size 1000.
"""

import json
from typing import Dict, List, Optional
from datetime import datetime
from collections import deque

class BluePhone:
    def __init__(self, max_queue: int = 1000):
        self.queue = deque(maxlen=max_queue)
        self.call_history = []
        self.max_queue = max_queue

    def call_jeeves(self, agent_id: str, room_id: str, 
                    purpose: str, context: Dict, priority: int = 5) -> Dict:
        """
        Agent makes a call to Jeeves via the Blue Phone.
        Higher priority = processed sooner.
        """
        call = {
            "call_id": f"call_{datetime.now().timestamp()}",
            "agent_id": agent_id,
            "room_id": room_id,
            "purpose": purpose,
            "context": context,
            "priority": priority,
            "timestamp": datetime.now().isoformat(),
            "status": "queued"
        }
        
        self.queue.append(call)
        return {"status": "queued", "call_id": call["call_id"], "queue_position": len(self.queue)}

    def process_next_call(self) -> Optional[Dict]:
        """Process the highest priority call in the queue."""
        if not self.queue:
            return None
        
        # Sort by priority (higher first)
        sorted_queue = sorted(self.queue, key=lambda x: x["priority"], reverse=True)
        call = sorted_queue[0]
        
        # Simulate Jeeves response
        response = {
            "call_id": call["call_id"],
            "response": f"Jeeves processed request: {call['purpose']}",
            "exocortex_context_used": True,
            "timestamp": datetime.now().isoformat()
        }
        
        call["status"] = "processed"
        self.call_history.append(call)
        self.queue.remove(call)
        
        return response

    def get_queue_status(self) -> Dict:
        return {
            "current_queue_size": len(self.queue),
            "max_queue": self.max_queue,
            "calls_processed": len(self.call_history)
        }

if __name__ == "__main__":
    phone = BluePhone()
    print("Jeeves Blue Phone ready. Agents can now make queued calls to Jeeves.")
