#!/usr/bin/env python3
"""
Jeeves Coordination Momentum Tracking
Tracks whether a coordinated effort is gaining or losing momentum over time.
"""

class JeevesCoordinationMomentumTracking:
    def __init__(self, master_map, exocortex):
        self.master_map = master_map
        self.exocortex = exocortex
        self.momentum_data = {}

    def update_momentum(self, objective_id: str, progress_delta: float):
        """Update momentum for an ongoing objective."""
        if objective_id not in self.momentum_data:
            self.momentum_data[objective_id] = []
        self.momentum_data[objective_id].append(progress_delta)

        self.exocortex.log_event("coordination_momentum_updated", {
            "objective_id": objective_id,
            "progress_delta": progress_delta
        })

    def get_momentum_status(self, objective_id: str):
        """Determine if momentum is positive, negative, or neutral."""
        deltas = self.momentum_data.get(objective_id, [])
        if not deltas:
            return {"status": "no_data"}

        avg_delta = sum(deltas) / len(deltas)
        if avg_delta > 0.05:
            return {"status": "positive_momentum", "objective_id": objective_id}
        elif avg_delta < -0.05:
            return {"status": "negative_momentum", "objective_id": objective_id}
        else:
            return {"status": "neutral_momentum", "objective_id": objective_id}
