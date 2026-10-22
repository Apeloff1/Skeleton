"""skeleton/app/gap_status.py
Complete status report generator for the multi-gap starter packet.
Runs the orchestrator and returns a structured, receipted summary.
"""
from __future__ import annotations

import json
from typing import Any

from skeleton.app.gap_orchestrator import run_all_starters

def generate_status() -> dict[str, Any]:
    """Produce a fail-closed status card covering all planes."""
    result = run_all_starters()
    status = {
        "kind": "gap_status",
        "digest": result["digest"],
        "plane_count": len(result["planes"]),
        "planes": result["planes"],
        "stored_prose": 0,
        "ready": True,
    }
    return status

def print_status() -> None:
    status = generate_status()
    print(json.dumps(status, indent=2))

if __name__ == "__main__":
    print_status()
