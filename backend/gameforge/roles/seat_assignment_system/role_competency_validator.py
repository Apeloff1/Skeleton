#!/usr/bin/env python3
"""
Role Competency Validator
Validates that each role seat has sufficient high-competency signals (coder style references, quality criteria, etc.).
Used as a quality gate before roles are assigned to live seats in rooms.
"""

import json
from typing import Dict, List, Any

class RoleCompetencyValidator:
    def __init__(self):
        self.minimum_coder_references = 2
        self.required_fields = [
            "role_id", "name", "category", "specialty", "perspective",
            "traits", "skills", "prompt_template", "quality_criteria",
            "coder_style_references", "competency_level"
        ]
    
    def validate_role(self, role: Dict) -> Dict[str, Any]:
        """Validate a single role for high competency."""
        issues = []
        score = 100
        
        # Check required fields
        for field in self.required_fields:
            if field not in role or not role[field]:
                issues.append(f"Missing or empty required field: {field}")
                score -= 15
        
        # Check coder style references (high competency signal)
        coder_refs = role.get("coder_style_references", [])
        if len(coder_refs) < self.minimum_coder_references:
            issues.append(f"Insufficient coder style references (has {len(coder_refs)}, needs {self.minimum_coder_references}+)")
            score -= 20
        
        # Check quality criteria depth
        quality = role.get("quality_criteria", [])
        if len(quality) < 2:
            issues.append("Quality criteria too shallow (needs 2+ specific criteria)")
            score -= 10
        
        # Check competency level
        if role.get("competency_level") != "expert":
            issues.append(f"Competency level is '{role.get('competency_level')}' instead of 'expert'")
            score -= 10
        
        return {
            "role_id": role.get("role_id", "unknown"),
            "name": role.get("name", "unknown"),
            "score": max(0, score),
            "issues": issues,
            "passed": len(issues) == 0 and score >= 80
        }
    
    def validate_category_roles(self, roles: List[Dict]) -> Dict[str, Any]:
        """Validate all roles in a category."""
        results = [self.validate_role(role) for role in roles]
        passed = sum(1 for r in results if r["passed"])
        avg_score = sum(r["score"] for r in results) / len(results) if results else 0
        
        return {
            "total_roles": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "average_score": round(avg_score, 1),
            "results": results
        }

if __name__ == "__main__":
    print("Role Competency Validator initialized.")
    print("Use validate_role() or validate_category_roles() to check role data sets.")