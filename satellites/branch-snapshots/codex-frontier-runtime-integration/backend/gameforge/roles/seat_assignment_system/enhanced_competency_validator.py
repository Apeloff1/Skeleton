#!/usr/bin/env python3
"""
Enhanced Competency Validator
Full production-grade validator for all Role-Seat data sets.
Checks coder style references, quality depth, prompt strength, and competency signals.
Generates actionable reports with specific improvement recommendations per role.
"""

import json
import os
from typing import Dict, List, Any
from datetime import datetime

class EnhancedCompetencyValidator:
    def __init__(self, roles_base_path: str):
        self.roles_base_path = roles_base_path
        self.results = []
        self.category_stats = {}
    
    def validate_role(self, role: Dict) -> Dict[str, Any]:
        issues = []
        recommendations = []
        score = 100
        
        # === Coder Style References (High value signal) ===
        coder_refs = role.get("coder_style_references", [])
        if len(coder_refs) < 2:
            issues.append(f"Only {len(coder_refs)} coder references (minimum 2 required for expert level)")
            recommendations.append("Add 2+ specific coder style references with clear application notes.")
            score -= 20
        elif len(coder_refs) >= 3:
            score += 5  # Bonus for strong references
        
        # === Quality Criteria Depth ===
        quality = role.get("quality_criteria", [])
        if len(quality) < 2:
            issues.append(f"Only {len(quality)} quality criteria (needs 2+ specific, measurable criteria)")
            recommendations.append("Expand quality criteria to be specific and measurable.")
            score -= 15
        
        # === Prompt Template Strength ===
        prompt = role.get("prompt_template", "")
        if len(prompt) < 120:
            issues.append("Prompt template too short or generic")
            recommendations.append("Make prompt template more specific and directive.")
            score -= 10
        
        # === Competency Level ===
        if role.get("competency_level") != "expert":
            issues.append(f"Competency level is '{role.get('competency_level')}' instead of 'expert'")
            recommendations.append("Set competency_level to 'expert' for all production roles.")
            score -= 10
        
        # === Perspective & Specialty Clarity ===
        if not role.get("perspective") or len(role.get("perspective", "")) < 40:
            issues.append("Perspective is too vague or missing")
            recommendations.append("Write a clear, specific perspective statement.")
            score -= 8
        
        passed = len(issues) == 0 and score >= 80
        
        return {
            "role_id": role.get("role_id", "unknown"),
            "name": role.get("name", "unknown"),
            "category": role.get("category", "unknown"),
            "score": max(0, min(100, score)),
            "passed": passed,
            "issues": issues,
            "recommendations": recommendations
        }
    
    def scan_all(self):
        """Scan every role JSON in the system."""
        print("Running full enhanced competency validation across all role data sets...")
        self.results = []
        
        for root, _, files in os.walk(self.roles_base_path):
            for file in files:
                if file.endswith(".json"):
                    path = os.path.join(root, file)
                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        for role in data.get("roles", []):
                            result = self.validate_role(role)
                            self.results.append(result)
                    except Exception as e:
                        print(f"Error reading {path}: {e}")
        
        print(f"Validation complete. {len(self.results)} roles analyzed.")
    
    def generate_full_report(self, output_path: str):
        """Generate comprehensive report with category breakdown and top fixes."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r["passed"])
        failed = total - passed
        avg_score = sum(r["score"] for r in self.results) / total if total > 0 else 0
        
        # Category breakdown
        cat_stats = {}
        for r in self.results:
            cat = r["category"]
            if cat not in cat_stats:
                cat_stats[cat] = {"total": 0, "passed": 0, "avg_score": 0, "scores": []}
            cat_stats[cat]["total"] += 1
            cat_stats[cat]["scores"].append(r["score"])
            if r["passed"]:
                cat_stats[cat]["passed"] += 1
        
        for cat in cat_stats:
            scores = cat_stats[cat]["scores"]
            cat_stats[cat]["avg_score"] = round(sum(scores) / len(scores), 1)
            cat_stats[cat]["pass_rate"] = round((cat_stats[cat]["passed"] / cat_stats[cat]["total"]) * 100, 1)
            del cat_stats[cat]["scores"]
        
        report = {
            "timestamp": datetime.utcnow().isoformat(),
            "summary": {
                "total_roles": total,
                "passed": passed,
                "failed": failed,
                "pass_rate_percent": round((passed / total) * 100, 1) if total > 0 else 0,
                "average_score": round(avg_score, 1)
            },
            "category_breakdown": cat_stats,
            "failed_roles_sample": [r for r in self.results if not r["passed"]][:20],
            "top_recommendations": self._aggregate_recommendations()
        }
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n=== COMPETENCY VALIDATION REPORT ===")
        print(f"Total Roles: {total}")
        print(f"Passed: {passed} ({report['summary']['pass_rate_percent']}%)")
        print(f"Average Score: {report['summary']['average_score']}")
        print(f"Report saved to: {output_path}")
    
    def _aggregate_recommendations(self) -> List[Dict]:
        rec_counts = {}
        for r in self.results:
            for rec in r.get("recommendations", []):
                rec_counts[rec] = rec_counts.get(rec, 0) + 1
        sorted_recs = sorted(rec_counts.items(), key=lambda x: x[1], reverse=True)
        return [{"recommendation": rec, "occurrences": count} for rec, count in sorted_recs[:10]]

if __name__ == "__main__":
    validator = EnhancedCompetencyValidator(
        roles_base_path="/home/workdir/artifacts/gameforge_v1/gameforge/roles"
    )
    validator.scan_all()
    validator.generate_full_report(
        "/home/workdir/artifacts/gameforge_v1/gameforge/roles/seat_assignment_system/full_competency_report.json"
    )