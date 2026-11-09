from __future__ import annotations
from typing import Any, Dict, List
import networkx as nx
from gameforge.roles.base_role import Role, RoleSet
from gameforge.roles.role_manager import RoleManager

class RoleCyclingEngine:
    """
    When an agent is 'seated' in a room, it cycles through the room's 100 roles.
    Each role evaluates, adds to, refines, and quality-controls the work.
    """

    def __init__(self, role_manager: RoleManager):
        self.role_manager = role_manager

    def cycle_roles(self, work: Dict[str, Any], room_category: str, agent_context: Dict[str, Any] = None,
                    strategy: str = "grouped") -> Dict[str, Any]:
        """
        Advanced Agentic Quality Control with multiple strategies.
        The seated agent must cycle through all 100 roles before any handoff.
        Each role evaluates, adds to, refines, and quality-controls the work.
        """
        role_set = self.role_manager.get_role_set(room_category)
        if not role_set.roles:
            role_set = self.role_manager.create_default_role_set(room_category)

        role_feedback = []
        current_work = work.copy()

        if strategy == "grouped":
            groups = self._group_roles_by_category(role_set.roles)
            for group_name, roles in groups.items():
                for role in roles:
                    feedback = role.apply(current_work, agent_context)
                    role_feedback.append(feedback)
                    current_work = self._apply_role_refinements(current_work, feedback)
                current_work[f"synthesis_{group_name}"] = f"Group synthesis from {group_name} completed."

        elif strategy == "sequential":
            for role in role_set.roles:
                feedback = role.apply(current_work, agent_context)
                role_feedback.append(feedback)
                current_work = self._apply_role_refinements(current_work, feedback)

        # Always run Final Synthesis Role at the end
        synthesis_feedback = self._run_final_synthesis(current_work, role_feedback)
        role_feedback.append(synthesis_feedback)
        current_work = self._apply_role_refinements(current_work, synthesis_feedback)

        final_work = {
            **current_work,
            "role_cycling_complete": True,
            "roles_cycled": len(role_set.roles),
            "cycling_strategy": strategy,
            "role_feedback_summary": self._summarize_feedback(role_feedback),
            "final_quality_score": self._calculate_final_score(role_feedback),
            "quality_gate_passed": self._check_quality_gate(role_feedback),
            "synthesis_notes": synthesis_feedback.get("notes", ""),
            "role_synergy_notes": self._detect_role_synergy(role_feedback),
            "audit_trail": [f["role"] for f in role_feedback],
            "contribution_map": self._build_contribution_map(role_feedback)
        }

        return final_work

    def _build_contribution_map(self, feedback_list: List[Dict]) -> Dict[str, List[str]]:
        """Map what each role contributed (additions, refinements, etc.)."""
        contrib = {}
        for f in feedback_list:
            role = f.get("role", "Unknown")
            contrib[role] = {
                "additions": f.get("additions", []),
                "refinements": f.get("refinements", []),
                "quality_score": f.get("quality_score", 0)
            }
        return contrib

    def _detect_role_synergy(self, feedback_list: List[Dict]) -> List[str]:
        """Simple synergy/conflict detection between roles."""
        notes = []
        roles = [f.get("role") for f in feedback_list]
        if "Performance Optimizer" in roles and "Edge Case Destroyer" in roles:
            notes.append("High synergy: Performance and robustness roles aligned well.")
        if len(set(roles)) < len(roles) * 0.8:
            notes.append("Warning: Some role overlap detected in feedback.")
        return notes

    def _group_roles_by_category(self, roles: List[Role]) -> Dict[str, List[Role]]:
        groups = {}
        for role in roles:
            cat = role.category
            if cat not in groups:
                groups[cat] = []
            groups[cat].append(role)
        return groups

    def _apply_role_refinements(self, work: Dict[str, Any], feedback: Dict[str, Any]) -> Dict[str, Any]:
        if feedback.get("refinements"):
            work.setdefault("refined_by", []).append(feedback["role"])
            work.setdefault("refinement_log", []).append(feedback)
        return work

    def _run_final_synthesis(self, work: Dict[str, Any], all_feedback: List[Dict]) -> Dict[str, Any]:
        """Final synthesis role that consolidates all previous role feedback."""
        return {
            "role": "Final Synthesis Role",
            "evaluation": "Consolidated feedback from all 100 roles.",
            "additions": ["Integrated cross-role insights"],
            "refinements": ["Final coherence pass completed"],
            "quality_score": self._calculate_final_score(all_feedback),
            "notes": "Final synthesis performed after full role cycle."
        }

    def _check_quality_gate(self, feedback_list: List[Dict]) -> bool:
        if not feedback_list:
            return False
        avg_score = sum(f.get("quality_score", 0) for f in feedback_list) / len(feedback_list)
        return avg_score >= 0.75  # Configurable threshold

    def _summarize_feedback(self, feedback_list: List[Dict]) -> Dict[str, Any]:
        if not feedback_list:
            return {}
        return {
            "total_roles": len(feedback_list),
            "average_score": sum(f.get("quality_score", 0) for f in feedback_list) / len(feedback_list),
            "roles_contributed": [f.get("role") for f in feedback_list],
            "lowest_scoring_role": min(feedback_list, key=lambda x: x.get("quality_score", 1)).get("role"),
            "highest_scoring_role": max(feedback_list, key=lambda x: x.get("quality_score", 0)).get("role")
        }

    def _calculate_final_score(self, feedback_list: List[Dict]) -> float:
        if not feedback_list:
            return 0.0
        return sum(f.get("quality_score", 0.7) for f in feedback_list) / len(feedback_list)

    def _summarize_feedback(self, feedback_list: List[Dict]) -> Dict[str, Any]:
        return {
            "total_roles": len(feedback_list),
            "average_score": sum(f.get("quality_score", 0) for f in feedback_list) / len(feedback_list) if feedback_list else 0,
            "roles_contributed": [f["role"] for f in feedback_list]
        }

    def _calculate_final_score(self, feedback_list: List[Dict]) -> float:
        if not feedback_list:
            return 0.0
        return sum(f.get("quality_score", 0.7) for f in feedback_list) / len(feedback_list)
