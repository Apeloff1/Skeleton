#!/usr/bin/env python3
"""
Snowball + Boardroom Vault Integration
Connects user choices logged in Snowball steps with the Boardroom Vault for game file management.
"""

from typing import Dict, Optional
from gameforge.snowball.snowball_step_logs import get_step_database, get_all_step_logs
from gameforge.boardroom.vault import boardroom_vault

class SnowballBoardroomBridge:
    def __init__(self):
        self.vault = boardroom_vault

    def save_game_file_from_snowball(self, step_id: str, filename: str, content: bytes, metadata: Dict = None):
        """Save a game file produced during a Snowball step into the Boardroom Vault."""
        step_db = get_step_database(step_id)
        if step_db:
            step_db.add_agent_note(f"Saved game file to Boardroom Vault: {filename}")
        
        entry = self.vault.put_file(filename, content, metadata={
            **(metadata or {}),
            "source_step": step_id,
            "snowball_origin": True
        })
        return entry

    def load_game_file_for_room(self, file_id: str, version: int = None) -> Optional[bytes]:
        """Allow any room/agent to retrieve a file from the vault."""
        return self.vault.get_file(file_id, version)

    def get_snowball_context_for_room(self, room_name: str) -> Dict:
        """Provide all Snowball step logs to any room so agents can augment building."""
        logs = get_all_step_logs()
        return {
            "room": room_name,
            "snowball_progress": logs,
            "available_vault_files": self.vault.list_files()
        }

# Global bridge
snowball_boardroom_bridge = SnowballBoardroomBridge()