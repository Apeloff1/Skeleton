#!/usr/bin/env python3
"""
Forge Logging System
Centralized logging for all forges (Asset Forge, Mechanic Forge, World Forge, Code Forge, etc.).
Logs actions, outputs, and decisions so they are visible across rooms.
"""

import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
import json
import os

@dataclass
class ForgeLogEntry:
    forge_name: str
    action: str
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    timestamp: float
    success: bool
    notes: str = ""

class ForgeLogger:
    def __init__(self, forge_name: str, base_path: str = "/tmp/forge_logs"):
        self.forge_name = forge_name
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)
        self.log_file = os.path.join(base_path, f"{forge_name}_log.json")
        self.entries: List[ForgeLogEntry] = self._load()

    def _load(self) -> List[ForgeLogEntry]:
        if os.path.exists(self.log_file):
            with open(self.log_file, "r") as f:
                data = json.load(f)
                return [ForgeLogEntry(**item) for item in data]
        return []

    def _save(self):
        with open(self.log_file, "w") as f:
            json.dump([asdict(e) for e in self.entries], f, indent=2)

    def log_action(self, action: str, input_data: Dict = None, output_data: Dict = None, 
                   success: bool = True, notes: str = ""):
        entry = ForgeLogEntry(
            forge_name=self.forge_name,
            action=action,
            input_data=input_data or {},
            output_data=output_data or {},
            timestamp=time.time(),
            success=success,
            notes=notes
        )
        self.entries.append(entry)
        self._save()
        print(f"[{self.forge_name}] {action} - Success: {success}")

    def get_recent_logs(self, limit: int = 20) -> List[Dict]:
        return [asdict(e) for e in self.entries[-limit:]]

    def get_all_logs(self) -> List[Dict]:
        return [asdict(e) for e in self.entries]

# Registry of common forges
FORGE_LOGGERS = {
    "asset_forge": ForgeLogger("AssetForge"),
    "mechanic_forge": ForgeLogger("MechanicForge"),
    "world_forge": ForgeLogger("WorldForge"),
    "code_forge": ForgeLogger("CodeForge"),
    "ui_forge": ForgeLogger("UIForge"),
    "balance_forge": ForgeLogger("BalanceForge"),
}

def get_forge_logger(forge_name: str) -> ForgeLogger:
    if forge_name in FORGE_LOGGERS:
        return FORGE_LOGGERS[forge_name]
    return ForgeLogger(forge_name)  # Create on demand

def get_all_forge_logs() -> Dict[str, List[Dict]]:
    """Returns logs from all forges - available to every room."""
    return {name: logger.get_all_logs() for name, logger in FORGE_LOGGERS.items()}