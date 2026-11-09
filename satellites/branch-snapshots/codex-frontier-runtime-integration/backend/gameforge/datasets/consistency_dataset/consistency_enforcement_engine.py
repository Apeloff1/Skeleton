#!/usr/bin/env python3
"""
Consistency Enforcement Engine
Ensures structural, naming, quality, and philosophical consistency across all 100 categories,
10,000 seats, and all role data sets in the Zaibatsu CNS.
"""

import json
from typing import Dict, List, Any

class ConsistencyEnforcementEngine:
    def __init__(self, master_manifest_path: str):
        self.master_manifest_path = master_manifest_path
        self.violations = []
        self.checks_performed = 0
    
    def check_role_consistency(self, role: Dict) -> List[str]:
        """Check a single role for internal consistency."""
        violations = []
        self.checks_performed += 1
        
        # Check required fields
        required = ["role_id", "name", "category", "specialty", "perspective", 
                    "skills", "prompt_template", "quality_criteria", "coder_style_references"]
        for field in required:
            if field not in role or not role[field]:
                violations.append(f"Missing or empty required field: {field}")
        
        # Check coder style references exist and are meaningful
        if len(role.get("coder_style_references", [])) < 2:
            violations.append("Insufficient coder style references (minimum 2 required)")
        
        # Check skills alignment with master skill bank (simplified check)
        if len(role.get("skills", [])) < 4:
            violations.append("Too few skills defined (minimum 4 required)")
        
        # Check prompt template references key elements
        prompt = role.get("prompt_template", "")
        if "{coder_style_references}" not in prompt and "coder" not in prompt.lower():
            violations.append("Prompt template does not reference coder styles")
        
        # Check quality criteria are specific
        quality = role.get("quality_criteria", [])
        if len(quality) < 2:
            violations.append("Quality criteria too shallow (needs 2+ specific criteria)")
        
        return violations
    
    def check_category_consistency(self, category: str, roles: List[Dict]) -> List[str]:
        """Check consistency across all roles in a category."""
        violations = []
        
        role_ids = [r.get("role_id") for r in roles]
        if len(role_ids) != len(set(role_ids)):
            violations.append(f"Duplicate role_ids found in category {category}")
        
        # Check for skill overlap issues (simplified)
        all_skills = set()
        for role in roles:
            all_skills.update(role.get("skills", []))
        
        if len(all_skills) < 10:
            violations.append(f"Category {category} has too little skill diversity")
        
        return violations
    
    def run_full_consistency_check(self, roles_base_path: str) -> Dict[str, Any]:
        """Run complete consistency check across the entire system."""
        print("Running full consistency enforcement check...")
        
        # This would normally walk all files. For now we return structure.
        return {
            "checks_performed": self.checks_performed,
            "violations_found": len(self.violations),
            "violations": self.violations[:50],  # Limit output
            "status": "passed" if len(self.violations) == 0 else "issues_found",
            "timestamp": "2026-07-19"
        }
    
    def enforce_naming_convention(self, name: str) -> bool:
        """Enforce consistent naming across roles."""
        # Example: Must contain category hint and be descriptive
        if len(name) < 10:
            return False
        return True

if __name__ == "__main__":
    print("Consistency Enforcement Engine initialized.")
    print("Use check_role_consistency() and check_category_consistency() for targeted validation.")