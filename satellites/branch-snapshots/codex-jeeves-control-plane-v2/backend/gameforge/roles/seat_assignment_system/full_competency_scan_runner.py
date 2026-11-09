#!/usr/bin/env python3
"""
Full Competency Scan Runner
Executes complete validation across all role data sets and generates actionable fix lists.
Designed to be run regularly as part of the quality pipeline.
"""

import json
from gameforge.roles.seat_assignment_system.enhanced_competency_validator import EnhancedCompetencyValidator

def run_full_scan():
    print("=== STARTING FULL COMPETENCY SCAN ===")
    
    validator = EnhancedCompetencyValidator(
        roles_base_path="/home/workdir/artifacts/gameforge_v1/gameforge/roles"
    )
    
    validator.scan_all()
    validator.generate_full_report(
        "/home/workdir/artifacts/gameforge_v1/gameforge/roles/seat_assignment_system/full_competency_report.json"
    )
    
    # Also generate a quick-fix summary for immediate action
    failed = [r for r in validator.results if not r["passed"]]
    print(f"\nQuick Summary:")
    print(f"- Total roles scanned: {len(validator.results)}")
    print(f"- Failed quality gate: {len(failed)}")
    print(f"- Top issues found in failed roles:")
    
    issue_counts = {}
    for r in failed:
        for issue in r["issues"]:
            issue_counts[issue] = issue_counts.get(issue, 0) + 1
    
    for issue, count in sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  • {issue} ({count} roles)")
    
    print("\nFull report saved. Use it to prioritize fixes.")

if __name__ == "__main__":
    run_full_scan()