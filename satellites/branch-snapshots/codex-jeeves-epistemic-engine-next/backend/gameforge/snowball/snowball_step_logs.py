#!/usr/bin/env python3
"""
Snowball Step Logs System
Per-step databases/logs for the Snowball game building process.
Logs user choices and makes them available to all rooms/agents.
"""

import time
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import json
import os

@dataclass
class SnowballStepLog:
    step_id: str
    step_name: str
    user_choices: Dict[str, Any]
    timestamp: float
    agent_notes: List[str]
    status: str  # "in_progress", "completed", "blocked"

class SnowballStepDatabase:
    def __init__(self, step_id: str, step_name: str, base_path: str = "/tmp/snowball_logs"):
        self.step_id = step_id
        self.step_name = step_name
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)
        self.log_file = os.path.join(base_path, f"{step_id}_log.json")
        self.log: SnowballStepLog = self._load_or_create()

    def _load_or_create(self) -> SnowballStepLog:
        if os.path.exists(self.log_file):
            with open(self.log_file, "r") as f:
                data = json.load(f)
                return SnowballStepLog(**data)
        else:
            log = SnowballStepLog(
                step_id=self.step_id,
                step_name=self.step_name,
                user_choices={},
                timestamp=time.time(),
                agent_notes=[],
                status="in_progress"
            )
            self._save(log)
            return log

    def _save(self, log: SnowballStepLog):
        with open(self.log_file, "w") as f:
            json.dump(asdict(log), f, indent=2)

    def record_user_choice(self, key: str, value: Any):
        """Record a user choice at this step."""
        self.log.user_choices[key] = value
        self.log.timestamp = time.time()
        self._save(self.log)
        print(f"[Snowball {self.step_id}] Recorded choice: {key} = {value}")

    def add_agent_note(self, note: str):
        """Agents in rooms can add notes visible to other rooms."""
        self.log.agent_notes.append({
            "timestamp": time.time(),
            "note": note
        })
        self._save(self.log)

    def complete_step(self):
        self.log.status = "completed"
        self.log.timestamp = time.time()
        self._save(self.log)
        print(f"[Snowball {self.step_id}] Step completed.")

    def get_log(self) -> Dict:
        return asdict(self.log)

# Registry of all snowball steps
SNOWBALL_STEPS = {
    "step_1_concept": "Game Concept & Genre",
    "step_2_mechanics": "Core Mechanics Design",
    "step_3_worldbuilding": "World & Narrative",
    "step_4_assets": "Asset Creation Pipeline",
    "step_5_systems": "Systems & Balance",
    "step_6_polish": "Polish & UX",
    "step_7_build": "Final Build & Export"
}

def get_step_database(step_key: str) -> Optional[SnowballStepDatabase]:
    if step_key in SNOWBALL_STEPS:
        return SnowballStepDatabase(step_key, SNOWBALL_STEPS[step_key])
    return None

def get_all_step_logs() -> Dict[str, Dict]:
    """Get logs from all steps - available to every room."""
    logs = {}
    for step_id, step_name in SNOWBALL_STEPS.items():
        db = get_step_database(step_id)
        if db:
            logs[step_id] = db.get_log()
    return logs