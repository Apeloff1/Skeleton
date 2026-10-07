#!/usr/bin/env python3
"""
ProjectOrchestrator (Cowabunga v4 adaptation) — long-horizon game creation.

Prompt Jeeves to create an entire game over a multi-month horizon. Jeeves
breaks the vision into phases → milestones → sprints, delegates specialised
agents, runs the autonomous workflow per phase, builds after every phase via
the InternalBuildSystem, enforces quality gates, and produces a MASTER FINAL
BUILD delivered through the JeevesVault.

Fully self-contained — no dependency on the missing orchestration.* modules.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from gameforge.workflow.autonomous_workflow import WorkflowRun
from gameforge.workflow.internal_build_system import create_internal_build_system
from gameforge.workflow.jeeves_vault import jeeves_vault
from gameforge.workflow.workflow_persistence import workflow_persistence

_HIGH_LEVEL_PHASES = [
    "Pre-Production & Prototyping",
    "Core Systems & Mechanics",
    "Level & Content Creation",
    "Narrative & Quest Integration",
    "Polish, Balance & Iteration",
    "Final Production & Release Prep",
]

_DELIVERABLES = {
    "Pre-Production & Prototyping": ["Core loop prototype", "Vertical slice", "Design pillars"],
    "Core Systems & Mechanics": ["Combat/mechanics systems", "Progression systems", "Core loops"],
    "Level & Content Creation": ["Procedural systems", "Hand-crafted levels", "Asset pipeline"],
    "Narrative & Quest Integration": ["Main story", "Side quests", "World lore"],
    "Polish, Balance & Iteration": ["Balance passes", "Performance optimisation", "Bug fixing"],
    "Final Production & Release Prep": ["Final polish", "Marketing assets", "Release build"],
}

_AGENT_ROLES = [
    ("level_design_lead", ["procedural_generation", "level_design", "game_design_patterns"]),
    ("systems_designer", ["mechanics_simulation", "balance", "systems_design"]),
    ("narrative_designer", ["quest_design", "world_building", "narrative"]),
    ("content_generator", ["procedural_generation", "quest_generation", "asset_creation"]),
    ("quality_assurance", ["game_content_evaluation", "playtesting", "balance"]),
]


class ProjectOrchestrator:
    def __init__(self, project_name: str):
        self.project_name = project_name
        self.phases: List[Dict] = []
        self.milestones: List[Dict] = []
        self.agents: Dict[str, Dict] = {}
        self.total_estimated_months = 0
        self.build_results: List[Dict] = []
        self.internal_build = create_internal_build_system(project_name)

    def create_full_game(self, user_prompt: str, time_budget_months: int = 6,
                         iterations_per_phase: int = 2, base_url: str = "") -> Dict:
        self.total_estimated_months = max(1, min(int(time_budget_months), 36))
        plan = self._create_project_plan(user_prompt, self.total_estimated_months)
        self._break_into_phases(plan, self.total_estimated_months)
        self._delegate_agents(plan)
        execution = self._execute_phases(user_prompt, iterations_per_phase)
        deployment = self._master_deployment(execution, base_url=base_url)

        result = {
            "project": self.project_name,
            "user_prompt": user_prompt,
            "time_budget_months": self.total_estimated_months,
            "project_plan": plan,
            "phases": self.phases,
            "milestones": self.milestones,
            "delegated_agents": self.agents,
            "execution": execution,
            "deployment": deployment,
            "status": "completed",
            "completed_at": time.time(),
        }
        workflow_persistence.save_run(self.project_name, {**result, "run_id": f"proj_{self.project_name}_{int(time.time()*1000)}", "kind": "project"})
        return result

    # ── planning ──────────────────────────────────────────────────────
    def _create_project_plan(self, user_prompt: str, months: int) -> Dict:
        return {
            "vision": user_prompt,
            "estimated_months": months,
            "core_pillars": ["gameplay", "narrative", "visuals", "systems", "balance"],
            "high_level_phases": list(_HIGH_LEVEL_PHASES),
            "risks": ["scope_creep", "technical_debt", "balance_issues"],
            "success_criteria": "Studio-quality, shippable game experience",
        }

    def _break_into_phases(self, plan: Dict, months: int):
        months_per_phase = max(1, months // len(plan["high_level_phases"]))
        for i, name in enumerate(plan["high_level_phases"]):
            self.phases.append({
                "phase_id": i + 1,
                "name": name,
                "estimated_months": months_per_phase,
                "sprints": 2 if months_per_phase > 1 else 1,
                "key_deliverables": _DELIVERABLES.get(name, ["Key deliverables"]),
                "quality_gate": round(0.80 + i * 0.02, 3),
            })
            self.milestones.append({
                "milestone_id": i + 1,
                "name": f"Complete {name}",
                "target_phase": i + 1,
                "success_criteria": f"Quality >= {round(0.80 + i * 0.02, 3)}",
            })

    def _delegate_agents(self, plan: Dict):
        for role, caps in _AGENT_ROLES:
            self.agents[role] = {
                "agent_id": f"{role}_{self.project_name}",
                "capabilities": caps,
                "status": "active",
            }

    # ── execution ───────────────────────────────────────────────────
    def _execute_phases(self, user_prompt: str, iterations_per_phase: int) -> Dict:
        phase_results: List[Dict] = []
        for phase in self.phases:
            run = WorkflowRun(
                f"{self.project_name}_p{phase['phase_id']}",
                f"{user_prompt} — focus: {phase['name']} ({', '.join(phase['key_deliverables'])})",
                max_iterations=max(1, min(int(iterations_per_phase), 4)),
            )
            wf = run.execute()
            quality = wf["final_quality"]

            build = self.internal_build.build_game(
                game_data={
                    "phase": phase["name"], "phase_id": phase["phase_id"],
                    "project": self.project_name, "quality": quality,
                    "deliverables": phase["key_deliverables"],
                },
                phase=f"phase_{phase['phase_id']}",
            )
            self.build_results.append({k: v for k, v in build.items() if k != "bundle_bytes"})

            gate_met = quality >= phase["quality_gate"]
            phase_results.append({
                "phase_id": phase["phase_id"],
                "name": phase["name"],
                "quality": quality,
                "quality_gate": phase["quality_gate"],
                "gate_met": gate_met,
                "iterations_run": wf["iterations_run"],
                "focus_systems": wf["focus_systems"],
                "build": {k: v for k, v in build.items() if k != "bundle_bytes"},
                "action": "advance" if gate_met else "re-iterate_recommended",
            })

        overall = round(sum(p["quality"] for p in phase_results) / max(len(phase_results), 1), 4)
        return {
            "phases_completed": len(phase_results),
            "phase_results": phase_results,
            "builds_performed": len(self.build_results),
            "overall_quality": overall,
            "all_gates_met": all(p["gate_met"] for p in phase_results),
        }

    def _master_deployment(self, execution: Dict, base_url: str = "") -> Dict:
        master = self.internal_build.build_game(
            game_data={
                "project": self.project_name,
                "type": "master_final_build",
                "phases_completed": execution["phases_completed"],
                "overall_quality": execution["overall_quality"],
                "phase_summary": [
                    {"name": p["name"], "quality": p["quality"]} for p in execution["phase_results"]
                ],
            },
            phase="master_final",
        )
        pkg = jeeves_vault.register(
            project_name=self.project_name,
            package_name=master["package_name"],
            package_bytes=master["bundle_bytes"],
            quality=execution["overall_quality"],
            architectures=master["architectures"],
            signature=master["signature"],
            metadata={"kind": "master_final_build", "phases": execution["phases_completed"]},
        )
        return {
            "master_build": {k: v for k, v in master.items() if k != "bundle_bytes"},
            "package": pkg,
            "delivery": jeeves_vault.delivery_link(pkg, base_url=base_url),
            "deploy_ready": execution["all_gates_met"],
        }


def create_project_orchestrator(project_name: str) -> ProjectOrchestrator:
    return ProjectOrchestrator(project_name)
