#!/usr/bin/env python3
"""
Jeeves Smart Delegation Engine
Uses context from MasterMap to intelligently suggest and delegate tools.
"""

class JeevesSmartDelegation:
    def __init__(self, master_map, tool_bank, exocortex):
        self.master_map = master_map
        self.tool_bank = tool_bank
        self.exocortex = exocortex

    def suggest_tools_for_agent(self, agent_id: str):
        """Analyze agent's current state and suggest useful tools."""
        position = self.master_map.agent_positions.get(agent_id)
        status = self.master_map.agent_status.get(agent_id, {})
        active_tools = status.get("active_tools", [])

        suggestions = []

        # Example logic
        if "CompassTool" not in active_tools and position:
            suggestions.append({
                "tool": "CompassTool",
                "reason": "Agent has no precision coordinate tool active"
            })

        if "InternalAgentGPSTool" not in active_tools:
            suggestions.append({
                "tool": "InternalAgentGPSTool",
                "reason": "Real-time GPS tracking recommended for better observability"
            })

        if status.get("load", 0) > 70:
            suggestions.append({
                "tool": "NegativeSpaceOrchestrationTool",
                "reason": "High load detected - recovery tool suggested"
            })

        return suggestions

    def auto_delegate_if_needed(self, agent_id: str):
        """Automatically delegate critical tools if conditions are met."""
        suggestions = self.suggest_tools_for_agent(agent_id)
        delegated = []

        for suggestion in suggestions:
            if suggestion["tool"] in ["CompassTool", "InternalAgentGPSTool"]:
                result = self.tool_bank.checkout_tool(
                    suggestion["tool"], 
                    "jeeves_auto_delegation", 
                    "jeeves"
                )
                if result["status"] == "checked_out":
                    delegated.append(suggestion["tool"])
                    self.exocortex.log_event("jeeves_auto_delegation", {
                        "agent_id": agent_id,
                        "tool": suggestion["tool"],
                        "reason": suggestion["reason"]
                    })

        return delegated
