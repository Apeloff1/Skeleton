#!/usr/bin/env python3
"""
Snowball Progress Tracker
Gives a clear overview of current Snowball state across all steps, questionnaire, and forges.
"""

from gameforge.snowball.snowball_step_logs import get_all_step_logs
from gameforge.snowball.questionnaire_logging import questionnaire_logger
from gameforge.forges.forge_logging import get_all_forge_logs

class SnowballProgressTracker:
    def __init__(self):
        self.step_logs = get_all_step_logs
        self.questionnaire = questionnaire_logger
        self.forge_logs = get_all_forge_logs

    def get_status(self) -> dict:
        step_logs = self.step_logs()
        completed_steps = sum(1 for log in step_logs.values() if log.get("status") == "completed")
        total_steps = len(step_logs)

        return {
            "questionnaire_completed": len(self.questionnaire.get_all_responses()) > 0,
            "snowball_progress": f"{completed_steps}/{total_steps} steps completed",
            "active_forge_activity": len(self.forge_logs()),
            "overall_status": "in_progress" if completed_steps < total_steps else "ready_for_build"
        }

    def print_status(self):
        status = self.get_status()
        print("\n=== Snowball Progress ===")
        print(f"Questionnaire: {'Done' if status['questionnaire_completed'] else 'Pending'}")
        print(f"Snowball Steps: {status['snowball_progress']}")
        print(f"Forge Activity: {status['active_forge_activity']} forges used")
        print(f"Overall: {status['overall_status'].upper()}")

# Global tracker
snowball_tracker = SnowballProgressTracker()