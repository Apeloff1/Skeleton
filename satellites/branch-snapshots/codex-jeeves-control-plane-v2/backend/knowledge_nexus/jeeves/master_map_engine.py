#!/usr/bin/env python3
"""
Jeeves MasterMap Engine
Central oversight map that aggregates all agents' GPS data and Nav Map state.
Part of the Exocortex.
"""

class MasterMapEngine:
    def __init__(self, nav_map, tool_bank, exocortex):
        self.nav_map = nav_map
        self.tool_bank = tool_bank
        self.exocortex = exocortex
        self.agent_positions = {}          # agent_id -> (x, y, z)
        self.agent_status = {}             # agent_id -> current role, load, tools
        self.historical_paths = {}         # agent_id -> list of positions

    def update_agent_position(self, agent_id: str, x: float, y: float, z: float = 0):
        """Update real-time position from InternalAgentGPSTool."""
        self.agent_positions[agent_id] = (x, y, z)
        if agent_id not in self.historical_paths:
            self.historical_paths[agent_id] = []
        self.historical_paths[agent_id].append((x, y, z))

        # Log to Exocortex
        self.exocortex.log_event("master_map_position_update", {
            "agent_id": agent_id,
            "position": (x, y, z)
        })

    def get_global_view(self):
        """Return full MasterMap state for Jeeves."""
        return {
            "agent_positions": self.agent_positions,
            "agent_status": self.agent_status,
            "nav_map_state": self.nav_map.get_current_state(),
            "timestamp": "now"
        }

    def delegate_tool(self, agent_id: str, tool_id: str, room_id: str = None):
        """Jeeves directly checks out and assigns a tool from Tool Bank."""
        result = self.tool_bank.checkout_tool(tool_id, room_id or "jeeves_delegation", "jeeves")
        if result["status"] == "checked_out":
            # Record delegation in Exocortex
            self.exocortex.log_event("tool_delegated_by_jeeves", {
                "agent_id": agent_id,
                "tool_id": tool_id,
                "room_id": room_id
            })
        return result
