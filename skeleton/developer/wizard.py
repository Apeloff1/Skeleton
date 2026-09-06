"""
Skeleton Developer CLI - Interactive Wizard

Provides interactive project setup, subsystem exploration,
and blueprint visualization for the Skeleton platform.
"""

import os
import sys
from enum import Enum, auto
from typing import Dict, List, Optional


class WizardMode(Enum):
    FULL = auto()
    QUICK = auto()
    EXPERT = auto()


class Wizard:
    """Interactive project builder and explorer."""

    def __init__(self, mode: WizardMode = WizardMode.FULL):
        self.mode = mode
        self.answers: Dict[str, str] = {}

    def run(self) -> str:
        """Run the wizard and return a summary."""
        lines = ["Skeleton Developer Wizard", "=" * 40, ""]

        if self.mode == WizardMode.QUICK:
            return self._quick_mode()
        elif self.mode == WizardMode.EXPERT:
            return self._expert_mode()
        else:
            return self._full_mode()

    def _quick_mode(self) -> str:
        """Quick mode: minimal questions, sensible defaults."""
        lines = ["Quick Mode", "-" * 20]
        self.answers["project_name"] = "my-skeleton-project"
        self.answers["template"] = "minimal-agent"
        self.answers["features"] = "core"
        lines.append(f"Project: {self.answers['project_name']}")
        lines.append(f"Template: {self.answers['template']}")
        lines.append("Created with defaults. Run with --mode=full for customization.")
        return "\n".join(lines)

    def _full_mode(self) -> str:
        """Full mode: step-by-step interactive setup."""
        lines = [
            "Full Mode - Interactive Setup",
            "-" * 30,
            "",
            "Step 1: Project Identity",
            "  Project name: [my-project]",
            "  Description:  [A skeleton-based project]",
            "",
            "Step 2: Template Selection",
            "  [1] minimal-agent      - Lightweight agent core",
            "  [2] game-forge         - Game development scaffold",
            "  [3] swarm-orchestrator - Multi-agent orchestration",
            "  [4] api-gateway        - REST API service template",
            "",
            "Step 3: Feature Modules",
            "  [x] forge       - Blueprint generation system",
            "  [x] intelligence - Agent reasoning layer",
            "  [ ] api          - REST API endpoints",
            "  [ ] testing      - Test harness and suites",
            "",
            "Step 4: Configuration",
            "  Python version: 3.11+",
            "  Async support:  enabled",
            "  Type hints:     strict",
            "",
            "Run 'skeleton dev scaffold <template>' to generate.",
        ]
        return "\n".join(lines)

    def _expert_mode(self) -> str:
        """Expert mode: expose all configuration options."""
        lines = [
            "Expert Mode - Advanced Configuration",
            "-" * 36,
            "",
            "Subsystem Explorer:",
        ]

        subsystems = self._list_subsystems()
        for name, path in subsystems.items():
            lines.append(f"  {name:20s} -> {path}")

        lines.extend([
            "",
            "Blueprint Registry:",
            "  Use 'skeleton dev visualize <module>' to inspect",
            "",
            "Custom Hooks:",
            "  pre-scaffold  - Run before project generation",
            "  post-scaffold - Run after project generation",
            "  pre-forge     - Run before blueprint compilation",
            "  post-forge    - Run after blueprint compilation",
        ])
        return "\n".join(lines)

    def _list_subsystems(self) -> Dict[str, str]:
        """Discover available subsystems in the skeleton package."""
        subsystems = {}
        try:
            import skeleton
            base = os.path.dirname(skeleton.__file__)
            for name in os.listdir(base):
                subpath = os.path.join(base, name)
                if os.path.isdir(subpath) and not name.startswith("_"):
                    subsystems[name] = subpath
        except Exception:
            pass
        return subsystems


class SubsystemExplorer:
    """Explore and document skeleton subsystems."""

    def __init__(self, subsystem: str):
        self.subsystem = subsystem

    def explore(self) -> str:
        """Return structured info about a subsystem."""
        lines = [f"Subsystem: {self.subsystem}", "=" * 40]

        try:
            module = __import__(f"skeleton.{self.subsystem}", fromlist=["__all__"])
            if hasattr(module, "__all__"):
                lines.append(f"Exported: {', '.join(module.__all__)}")
            else:
                lines.append("No __all__ defined")

            for attr in sorted(dir(module)):
                if not attr.startswith("_"):
                    obj = getattr(module, attr)
                    if isinstance(obj, type):
                        lines.append(f"  [class]  {attr}")
                    elif callable(obj):
                        lines.append(f"  [func]   {attr}")
        except ImportError as e:
            lines.append(f"Error loading subsystem: {e}")

        return "\n".join(lines)
