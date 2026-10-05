#!/usr/bin/env python3
"""
Jeeves Tool Delegation System
Allows Jeeves to directly access the Tool Bank and delegate tools to agents/rooms.
Increases delegation power and observability.
"""

class JeevesToolDelegation:
    def __init__(self, tool_bank, master_map, exocortex):
        self.tool_bank = tool_bank
        self.master_map = master_map
        self.exocortex = exocortex

    def delegate_tool_to_agent(self, agent_id: str, tool_id: str, room_id: str = None, reason: str = None):
        """Jeeves checks out a tool and assigns it to an agent."""
        checkout = self.tool_bank.checkout_tool(tool_id, room_id or "jeeves_delegation", "jeeves")
        
        if checkout["status"] == "checked_out":
            # Record in MasterMap and Exocortex
            self.master_map.agent_status[agent_id] = self.master_map.agent_status.get(agent_id, {})
            self.master_map.agent_status[agent_id]["active_tools"] = self.master_map.agent_status[agent_id].get("active_tools", [])
            self.master_map.agent_status[agent_id]["active_tools"].append(tool_id)

            self.exocortex.log_event("jeeves_tool_delegation", {
                "agent_id": agent_id,
                "tool_id": tool_id,
                "room_id": room_id,
                "reason": reason
            })

            return {
                "status": "delegated",
                "agent_id": agent_id,
                "tool_id": tool_id,
                "reason": reason
            }
        
        return checkout

    def recall_tool_from_agent(self, agent_id: str, tool_id: str):
        """Jeeves forces return of a tool from an agent back to Tool Bank."""
        return_result = self.tool_bank.return_tool(tool_id, usage_data={"recalled_by": "jeeves"})

        if agent_id in self.master_map.agent_status:
            if "active_tools" in self.master_map.agent_status[agent_id]:
                if tool_id in self.master_map.agent_status[agent_id]["active_tools"]:
                    self.master_map.agent_status[agent_id]["active_tools"].remove(tool_id)

        self.exocortex.log_event("jeeves_tool_recall", {
            "agent_id": agent_id,
            "tool_id": tool_id
        })

        return return_result
