"""Skeleton developer CLI package.

Provides the public developer-tooling surface for scaffolding, interactive
project planning, subsystem inspection, and command dispatch.
"""

from skeleton.developer.scaffold import ScaffoldEngine, list_templates
from skeleton.developer.wizard import (
    BlueprintVisualizer,
    ProjectWizard,
    SubsystemCard,
    SubsystemExplorer,
    WizardStep,
)
from skeleton.developer.commands import DevCommandRegistry, run_dev_command

# Compatibility aliases for the historical package-level names. The current
# implementations are ProjectWizard and DevCommandRegistry respectively.
Wizard = ProjectWizard
CommandRegistry = DevCommandRegistry

__all__ = [
    "ScaffoldEngine",
    "list_templates",
    "ProjectWizard",
    "Wizard",
    "WizardStep",
    "SubsystemCard",
    "SubsystemExplorer",
    "BlueprintVisualizer",
    "DevCommandRegistry",
    "CommandRegistry",
    "run_dev_command",
]
