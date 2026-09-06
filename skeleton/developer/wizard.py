"""
Skeleton Developer CLI — Interactive wizard and subsystem explorer

Provides:
- Interactive project creation wizard
- Subsystem discovery and health reporting
- Blueprint visualization helpers
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton.api.server import get_state
from skeleton.kernel.events import EventBus


@dataclass
class WizardStep:
    """Single step in an interactive wizard."""
    id: str
    question: str
    options: List[str]
    allow_freeform: bool = False
    default: Optional[str] = None


class ProjectWizard:
    """Interactive wizard for creating new Skeleton projects."""

    STEPS = [
        WizardStep(
            id="project_type",
            question="What kind of project are you building?",
            options=[
                "minimal-agent",
                "game-forge",
                "swarm-orchestrator",
                "custom",
            ],
            default="minimal-agent",
        ),
        WizardStep(
            id="project_name",
            question="Project name (lowercase, no spaces):",
            options=[],
            allow_freeform=True,
            default="my-skeleton-project",
        ),
        WizardStep(
            id="subsystem_bundle",
            question="Which subsystems should be pre-wired?",
            options=[
                "memory (RAG+CAG+MAG)",
                "intelligence (orchestrator + adaptive)",
                "swarm (mesh + negotiation)",
                "resilience (fortress + canary)",
                "observability (metrics + tracing)",
                "all",
            ],
            default="all",
        ),
        WizardStep(
            id="target_platform",
            question="Primary output target?",
            options=["json", "godot", "web", "custom"],
            default="json",
        ),
    ]

    def __init__(self, engine: Any):
        self.engine = engine
        self.answers: Dict[str, str] = {}

    def run(self, answers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Run the wizard, optionally with pre-filled answers."""
        self.answers = answers or {}

        for step in self.STEPS:
            if step.id not in self.answers:
                self.answers[step.id] = self._ask(step)

        return self._generate_plan()

    def _ask(self, step: WizardStep) -> str:
        """Present a step and collect input."""
        print(f"\n[Wizard] {step.question}")
        if step.options:
            for i, opt in enumerate(step.options, 1):
                marker = " (default)" if opt == step.default else ""
                print(f"  {i}. {opt}{marker}")
            prompt = f"Choice [1-{len(step.options)}]: "
        else:
            prompt = f"Enter value [{step.default}]: "

        try:
            response = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nWizard cancelled.")
            sys.exit(1)

        if not response and step.default:
            return step.default

        if step.options and response.isdigit():
            idx = int(response) - 1
            if 0 <= idx < len(step.options):
                return step.options[idx]

        return response or step.default or ""

    def _generate_plan(self) -> Dict[str, Any]:
        """Generate a project plan from wizard answers."""
        return {
            "project_name": self.answers.get("project_name", "my-project"),
            "template": self.answers.get("project_type", "minimal-agent"),
            "subsystems": self._parse_subsystems(self.answers.get("subsystem_bundle", "all")),
            "target": self.answers.get("target_platform", "json"),
            "next_steps": [
                f"Run: skeleton dev scaffold {self.answers.get('project_name')} --template {self.answers.get('project_type')}",
                "Edit config/settings.yaml",
                "Run: skeleton dev health",
            ],
        }

    @staticmethod
    def _parse_subsystems(bundle: str) -> List[str]:
        if bundle == "all":
            return ["memory", "intelligence", "swarm", "resilience", "observability", "cortex"]
        return [s.strip().split()[0] for s in bundle.split(",") if s.strip()]


@dataclass
class SubsystemCard:
    """Health card for a single subsystem."""
    name: str
    status: str
    phase: str
    handles: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    last_event: Optional[str] = None


class SubsystemExplorer:
    """Discover and report on all wired subsystems."""

    PHASE_ORDER = ["kernel", "memory", "intelligence", "swarm", "resilience", "interface", "cortex"]

    def __init__(self, state: Any = None):
        self.state = state or get_state()

    def discover(self) -> List[SubsystemCard]:
        """Build health cards for all wired subsystems."""
        cards: List[SubsystemCard] = []

        genesis = getattr(self.state, "genesis", None)
        if genesis is None:
            return [SubsystemCard(name="genesis", status="failed", phase="kernel", handles=[])]

        for phase in genesis.report.phases:
            wired = genesis.report.wired.get(phase, [])
            for handle_name in wired:
                handle = genesis.handles.get(handle_name)
                status = self._check_handle(handle)
                cards.append(SubsystemCard(
                    name=handle_name,
                    status=status,
                    phase=phase,
                    handles=[h for h in wired],
                    metrics=self._gather_metrics(handle),
                ))

        return cards

    @staticmethod
    def _check_handle(handle: Any) -> str:
        if handle is None:
            return "failed"
        if hasattr(handle, "health"):
            try:
                h = handle.health()
                return "healthy" if h.get("healthy", True) else "degraded"
            except Exception:
                return "degraded"
        if hasattr(handle, "stats"):
            return "healthy"
        return "unknown"

    @staticmethod
    def _gather_metrics(handle: Any) -> Dict[str, Any]:
        metrics: Dict[str, Any] = {}
        if hasattr(handle, "stats"):
            try:
                stats = handle.stats()
                if isinstance(stats, dict):
                    metrics.update(stats)
            except Exception:
                pass
        return metrics

    def summary(self) -> Dict[str, Any]:
        """Aggregate health summary."""
        cards = self.discover()
        by_status: Dict[str, int] = {}
        for c in cards:
            by_status[c.status] = by_status.get(c.status, 0) + 1

        return {
            "total_subsystems": len(cards),
            "phases_booted": len({c.phase for c in cards}),
            "status_breakdown": by_status,
            "overall": "healthy" if by_status.get("failed", 0) == 0 and by_status.get("degraded", 0) == 0 else "degraded",
            "cards": [asdict(c) for c in cards],
        }

    def render_table(self) -> str:
        """Render a human-readable table of subsystem health."""
        cards = self.discover()
        lines = [
            "+-----------------------------------------------------------------------+",
            "| Subsystem           | Phase       | Status      | Handles             |",
            "+---------------------+-------------+-------------+---------------------+",
        ]

        for card in cards:
            status_icon = {"healthy": "OK", "degraded": "WARN", "failed": "FAIL", "unknown": "?"}.get(card.status, "?")
            handles_str = ", ".join(card.handles[:3])
            if len(card.handles) > 3:
                handles_str += f" (+{len(card.handles) - 3})"
            lines.append(
                f"| {card.name:<19} | {card.phase:<11} | {status_icon:<3} {card.status:<8} | {handles_str:<19} |"
            )

        lines.append(
            "+-----------------------------------------------------------------------+"
        )
        return "\n".join(lines)


class BlueprintVisualizer:
    """Text-based blueprint visualization."""

    @staticmethod
    def render(blueprint: Any, compact: bool = False) -> str:
        """Render a blueprint as structured text."""
        if not hasattr(blueprint, "components"):
            return "Invalid blueprint object"

        lines = [
            f"Blueprint: {getattr(blueprint, 'name', 'unnamed')}",
            f"ID: {getattr(blueprint, 'blueprint_id', 'unknown')}",
            f"Components: {len(blueprint.components)}",
            f"Wires: {len(blueprint.wires)}",
            "",
        ]

        if compact:
            for cid, comp in blueprint.components.items():
                ports = ", ".join(f"{p.name}({p.direction})" for p in comp.ports)
                lines.append(f"  [{comp.kind}] {cid}: {ports}")
            return "\n".join(lines)

        lines.append("Components:")
        for cid, comp in blueprint.components.items():
            lines.append(f"  [] {cid} ({comp.kind})")
            for port in comp.ports:
                arrow = ">" if port.direction == "out" else "<"
                lines.append(f"      {arrow} {port.name}: {port.port_type}")

        if blueprint.wires:
            lines.append("")
            lines.append("Wires:")
            for wire in blueprint.wires:
                lines.append(f"  {wire.src[0]}.{wire.src[1]} -> {wire.dst[0]}.{wire.dst[1]}")

        return "\n".join(lines)

    @staticmethod
    def render_topology(blueprint: Any) -> Dict[str, Any]:
        """Export topology as JSON-serializable structure."""
        if hasattr(blueprint, "to_dict"):
            return blueprint.to_dict()
        return {"error": "Blueprint does not support to_dict()"}
