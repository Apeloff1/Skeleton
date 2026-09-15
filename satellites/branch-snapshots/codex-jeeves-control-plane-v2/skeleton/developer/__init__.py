"""
Skeleton Developer CLI Package

Provides developer tooling for the Skeleton platform:
  - scaffold: Project templates and generation
  - wizard:   Interactive project builder
  - commands: Command registry and dispatch
  - cli:      Main entry point

Usage:
    from skeleton.developer import ScaffoldEngine, Wizard
    engine = ScaffoldEngine()
    engine.create_project("minimal-agent", "my-project")
"""

from skeleton.developer.scaffold import ScaffoldEngine, list_templates
from skeleton.developer.wizard import Wizard, WizardMode, SubsystemExplorer
from skeleton.developer.commands import CommandRegistry

__all__ = [
    "ScaffoldEngine",
    "list_templates",
    "Wizard",
    "WizardMode",
    "SubsystemExplorer",
    "CommandRegistry",
]
