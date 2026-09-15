#!/usr/bin/env python3
"""
Jeeves Risk Early Warning System
Uses MasterMap data to detect emerging risks at the earliest possible stage.
"""

class JeevesRiskEarlyWarning:
    def __init__(self, master_map, exocortex):
        self.master_map = master_map
        self.exocortex = exocortex

    def scan_for_early_warnings(self):
        """Look for subtle early signs of future problems."""
        warnings = []

        # Example: rising load in a specific cluster over time
        for agent_id, status in self.master_map.agent_status.items():
            load = status.get("load", 0)
            if load > 60 and load < 75:
                warnings.append({
                    "type": "rising_load",
                    "agent_id": agent_id,
                    "severity": "low",
                    "message": "Load is rising — consider preemptive support"
                })

        if warnings:
            self.exocortex.log_event("early_warning_detected", {
                "warnings": warnings
            })

        return warnings
