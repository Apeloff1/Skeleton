#!/usr/bin/env python3
"""
CNS Execution Orchestrator
High-level script to coordinate major CNS operations:
- Run full competency + consistency scans
- Trigger mass enhanced role generation
- Activate agent assignment loops
- Apply reputation decay and update leaderboards

This is the main entry point for running the full Zaibatsu CNS at scale.
Path-robust: resolves the gameforge roles/manifest relative to this file so it
works inside the deployed backend (no hardcoded /home/workdir paths).
"""

import os

from gameforge.cns_full_integration_layer import CNSFullIntegrationLayer
from gameforge.roles.seat_assignment_system.enhanced_competency_validator import EnhancedCompetencyValidator
from gameforge.datasets.consistency_dataset.consistency_enforcement_engine import ConsistencyEnforcementEngine
from gameforge.roles.seat_assignment_system.reputation_decay_leaderboard import ReputationDecayLeaderboardSystem

# gameforge package root (this file lives at gameforge/cns_execution_orchestrator.py)
_GF_ROOT = os.path.dirname(os.path.abspath(__file__))
_ROLES_PATH = os.path.join(_GF_ROOT, "roles")
_MANIFEST_PATH = os.path.join(_GF_ROOT, "cns_master_manifest.json")


def run_full_cns_cycle():
    print("=== STARTING FULL CNS EXECUTION CYCLE ===")
    summary = {}

    # 1. Load integration layer
    cns = CNSFullIntegrationLayer()
    cns.load_all_components()
    summary["integration"] = cns.get_system_summary()

    # 2. Run competency validation
    validator = EnhancedCompetencyValidator(roles_base_path=_ROLES_PATH)
    validator.scan_all()
    report_path = os.path.join(_ROLES_PATH, "seat_assignment_system", "full_competency_report.json")
    try:
        if validator.results:
            os.makedirs(os.path.dirname(report_path), exist_ok=True)
            validator.generate_full_report(report_path)
    except Exception as e:  # noqa: BLE001
        print(f"competency report skipped: {e}")
    summary["competency"] = {"roles_analyzed": len(validator.results)}

    # 3. Run consistency enforcement
    consistency = ConsistencyEnforcementEngine(master_manifest_path=_MANIFEST_PATH)
    consistency_report = consistency.run_full_consistency_check(roles_base_path=_ROLES_PATH)
    summary["consistency"] = {
        "status": consistency_report.get("status"),
        "violations": consistency_report.get("violations_found", 0),
    }

    # 4. Apply reputation decay and update leaderboards
    reputation_system = ReputationDecayLeaderboardSystem()
    decayed = reputation_system.apply_reputation_decay()
    global_board = reputation_system.get_global_leaderboard(top_n=10)
    summary["reputation"] = {"decayed_agents": decayed, "leaderboard_size": len(global_board)}

    print("=== FULL CNS CYCLE COMPLETE ===")
    return {"ok": True, "cycle": "complete", **summary}


if __name__ == "__main__":
    run_full_cns_cycle()
