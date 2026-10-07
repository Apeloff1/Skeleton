#!/usr/bin/env python3
"""
Competency Validation Runner
Scans all role data sets, validates competency signals (coder references, depth, quality criteria),
and generates a detailed pass/fail report with improvement recommendations.
"""

import json
import os
from typing import Dict, List, Any
from datetime import datetime

class CompetencyValidationRunner:
    def __init__(self, roles_base_path: str):
        self.roles_base_path = roles_base_path
        self.results = []
        self.minimum_coder_refs = 2
        self.minimum_quality_criteria = 2
    
    def validate_single_role(self, role: Dict) -> Dict[str, Any]:
        issues = []
        score = 100
        
        # Check for coder_style_references
        coder_refs = role.get("coder_style_references", [])
        if len(coder_refs) < self.minimum_coder_refs:
            issues.append(f"Only {len(coder_refs)} coder style references (need {self.minimum_coder_refs}+)")
            score -= 25
        
        # Check quality_criteria depth
        quality = role.get("quality_criteria", [])
        if len(quality) < self.minimum_quality_criteria:
            issues.append(f"Only {len(quality)} quality criteria (need {self.minimum_quality_criteria}+)")
            score -= 15
        
        # Check for competency_level
        if role.get("competency_level") != "expert":
            issues.append(f"Competency level is '{role.get('competency_level')}' (should be 'expert')")
            score -= 10
        
        # Check prompt_template quality
        prompt = role.get("prompt_template", "")
        if len(prompt) < 150:
            issues.append("Prompt template too short or shallow")
            score -= 10
        
        passed = len(issues) == 0 and score >= 75
        
        return {
            "role_id": role.get("role_id", "unknown"),
            "name": role.get("name", "unknown"),
            "category": role.get("category", "unknown"),
            "score": max(0, score),
            "passed": passed,
            "issues": issues
        }
    
    def scan_and_validate(self):
        """Scan all role JSON files and validate them."""
        print("Starting full competency validation scan...")
        self.results = []
        
        for root, dirs, files in os.walk(self.roles_base_path):
            for file in files:
                if file.endswith('.json'):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        roles = data.get("roles", [])
                        for role in roles:
                            result = self.validate_single_role(role)
                            self.results.append(result)
                    except Exception as e:
                        print(f"Error processing {filepath}: {e}")
        
        print(f"Validation complete. {len(self.results)} roles scanned.")
    
    def generate_report(self, output_path: str):
        """Generate a detailed validation report."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r["passed"])
        failed = total - passed
        avg_score = sum(r["score"] for r in self.results) / total if total > 0 else 0
        
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "summary": {
                "total_roles_scanned": total,
                "passed": passed,
                "failed": failed,
                "pass_rate": round((passed / total) * 100, 1) if total > 0 else 0,
                "average_score": round(avg_score, 1)
            },
            "failed_roles": [r for r in self.results if not r["passed"]],
            "top_issues": self._get_top_issues()
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"Report generated: {output_path}")
        print(f"Pass rate: {report['summary']['pass_rate']}% | Average score: {report['summary']['average_score']}")
    
    def _get_top_issues(self) -> List[Dict]:
        issue_counts = {}
        for result in self.results:
            for issue in result["issues"]:
                issue_counts[issue] = issue_counts.get(issue, 0) + 1
        
        sorted_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)
        return [{"issue": issue, "count": count} for issue, count in sorted_issues[:10]]

if __name__ == "__main__":
    runner = CompetencyValidationRunner(
        roles_base_path="/home/workdir/artifacts/gameforge_v1/gameforge/roles"
    )
    runner.scan_and_validate()
    runner.generate_report(
        "/home/workdir/artifacts/gameforge_v1/gameforge/roles/seat_assignment_system/competency_validation_report.json"
    )