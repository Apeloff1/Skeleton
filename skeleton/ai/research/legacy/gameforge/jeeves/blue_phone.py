from __future__ import annotations
from typing import Any, Dict, List, Optional
import queue
import time

class BluePhone:
    """
    Direct high-priority consulting and strategy channel from Room Teams to Jeeves.
    Supports queued calls to prevent overwhelming Jeeves.
    Also forwards important consultations to the global ExoCortex for long-term memory.
    """

    def __init__(self, jeeves_instance: Any, max_queue_size: int = 50):
        self.jeeves = jeeves_instance
        self.consultation_log: List[Dict] = []
        self.call_queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self.exocortex_memory: List[Dict] = []  # Placeholder for global ExoCortex storage

    def call(self, room_id: str, query: str, context: Optional[Dict] = None, priority: str = "high") -> Dict[str, Any]:
        """
        Team calls Jeeves via Blue Phone.
        If Jeeves is busy, the call is queued.
        Important consultations are also stored in the ExoCortex.
        """
        consultation = {
            "room_id": room_id,
            "query": query,
            "context": context or {},
            "priority": priority,
            "timestamp": time.time()
        }

        # Queue the call if needed (simple backpressure)
        try:
            self.call_queue.put_nowait(consultation)
        except queue.Full:
            return {
                "status": "queued_full",
                "message": "Jeeves is currently overloaded. Call queued for later processing."
            }

        # Process the call (simulated immediate response for high priority)
        response = {
            "consultation_id": f"blue_{len(self.consultation_log) + 1}",
            "room_id": room_id,
            "jeeves_guidance": f"Strategic advice for: {query}",
            "recommended_actions": [
                "Re-evaluate from a systems and long-term perspective",
                "Consider implications before peer review voting",
                "Align with overall project strategy"
            ],
            "priority": priority,
            "timestamp": time.time()
        }

        self.consultation_log.append({
            "consultation": consultation,
            "response": response
        })

        # Store a copy in the ExoCortex (global memory)
        self._store_in_exocortex(consultation, response)

        return response

    def _store_in_exocortex(self, consultation: Dict, response: Dict):
        """Store consultation in the global ExoCortex memory layer."""
        exocortex_entry = {
            "type": "blue_phone_consultation",
            "room_id": consultation["room_id"],
            "query": consultation["query"],
            "jeeves_guidance": response.get("jeeves_guidance"),
            "timestamp": consultation["timestamp"]
        }
        self.exocortex_memory.append(exocortex_entry)
        # In a full system, this would write to the global exocortex vector/graph store

    def process_queue(self, max_items: int = 10) -> List[Dict]:
        """Process queued Blue Phone calls (rate-limited)."""
        processed = []
        for _ in range(max_items):
            try:
                consultation = self.call_queue.get_nowait()
                # Simulate processing
                processed.append({
                    "consultation": consultation,
                    "status": "processed"
                })
            except queue.Empty:
                break
        return processed

    def get_recent_consultations(self, room_id: Optional[str] = None, limit: int = 10) -> List[Dict]:
        if room_id:
            return [c for c in self.consultation_log if c["consultation"]["room_id"] == room_id][-limit:]
        return self.consultation_log[-limit:]

    def get_exocortex_consultations(self, limit: int = 20) -> List[Dict]:
        return self.exocortex_memory[-limit:]

    def get_consultation_log_summary(self) -> Dict[str, Any]:
        return {
            "total_consultations": len(self.consultation_log),
            "queued_calls": self.call_queue.qsize(),
            "exocortex_entries": len(self.exocortex_memory)
        }
