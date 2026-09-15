#!/usr/bin/env python3
"""
Room Toolbox Checkout Manager
Manages temporary tools inside a room's Toolbox after being checked out from the Tool Bank.
"""

class RoomToolboxCheckoutManager:
    def __init__(self, room_id: str):
        self.room_id = room_id
        self.active_tools = {}        # tool_id -> {agent_id, version, checked_out_at}
        self.usage_logs = []

    def add_tool(self, agent_id: str, tool_id: str, version: str = "latest"):
        self.active_tools[tool_id] = {
            "agent_id": agent_id,
            "version": version,
            "checked_out_at": "now"
        }

    def remove_tool(self, agent_id: str, tool_id: str):
        if tool_id in self.active_tools:
            del self.active_tools[tool_id]

    def log_tool_usage(self, agent_id: str, tool_id: str, usage_data: dict):
        self.usage_logs.append({
            "agent_id": agent_id,
            "tool_id": tool_id,
            "usage_data": usage_data,
            "timestamp": "now"
        })

    def get_active_tools_for_agent(self, agent_id: str):
        return {tid: data for tid, data in self.active_tools.items() if data["agent_id"] == agent_id}
