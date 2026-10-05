#!/usr/bin/env python3
"""
Snowball Full Integration Layer
Connects Questionnaire logging, Forge logging, Git/GitHub, and Deployment Pipeline.
"""

from typing import Dict
from gameforge.snowball.questionnaire_logging import questionnaire_logger
from gameforge.forges.forge_logging import get_all_forge_logs
from gameforge.snowball.snowball_step_logs import get_all_step_logs
from gameforge.snowball.git_github_integration import git_github
from gameforge.deployment.deployment_pipeline import deployment_pipeline

class SnowballFullIntegration:
    def __init__(self):
        self.questionnaire = questionnaire_logger
        self.forge_logs = get_all_forge_logs
        self.step_logs = get_all_step_logs
        self.git = git_github
        self.deployment = deployment_pipeline

    def get_full_build_context(self) -> Dict:
        """Returns everything an agent or the final build stage might need."""
        return {
            "questionnaire_responses": self.questionnaire.get_all_responses(),
            "snowball_step_logs": self.step_logs(),
            "forge_activity": self.forge_logs(),
            "git_history": self.git.get_commit_history(5)
        }

    def complete_snowball_and_deploy(self, game_name: str):
        """End-to-end: Mark Snowball complete + deploy builds."""
        # Log final questionnaire if needed
        self.questionnaire.log_response(
            "final_confirmation", 
            "Ready to build and deploy?", 
            True
        )
        
        # Deploy
        result = self.deployment.deploy_game(game_name)
        return result

# Global integration instance
snowball_full_integration = SnowballFullIntegration()