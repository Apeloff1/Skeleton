#!/usr/bin/env python3
"""
Jeeves Delegation Learning
Simple learning layer so Jeeves gets better at tool delegation over time based on outcomes.
"""

class JeevesDelegationLearning:
    def __init__(self, exocortex):
        self.exocortex = exocortex
        self.delegation_outcomes = {}  # tool_id -> list of success/failure records

    def record_delegation_outcome(self, agent_id: str, tool_id: str, success: bool, context: dict):
        if tool_id not in self.delegation_outcomes:
            self.delegation_outcomes[tool_id] = []
        
        self.delegation_outcomes[tool_id].append({
            "agent_id": agent_id,
            "success": success,
            "context": context,
            "timestamp": "now"
        })

        self.exocortex.log_event("delegation_outcome_recorded", {
            "tool_id": tool_id,
            "success": success
        })

    def get_tool_effectiveness(self, tool_id: str):
        records = self.delegation_outcomes.get(tool_id, [])
        if not records:
            return {"effectiveness": "unknown", "sample_size": 0}

        successes = sum(1 for r in records if r["success"])
        return {
            "effectiveness": successes / len(records),
            "sample_size": len(records)
        }

    def suggest_improvements(self):
        """Basic analysis of which tools are underperforming."""
        suggestions = []
        for tool_id, records in self.delegation_outcomes.items():
            effectiveness = self.get_tool_effectiveness(tool_id)
            if effectiveness["sample_size"] > 10 and effectiveness["effectiveness"] < 0.6:
                suggestions.append({
                    "tool_id": tool_id,
                    "issue": "Low effectiveness",
                    "recommendation": "Consider evolving this tool or restricting its use cases"
                })
        return suggestions
