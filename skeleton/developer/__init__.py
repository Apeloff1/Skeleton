"""
Skeleton Developer CLI Package.

Provides developer tooling for the Skeleton platform:
  - scaffold: Project templates and generation
  - wizard:   Interactive project builder
  - commands: Command registry and dispatch
  - cli:      Main entry point

Usage:
    from skeleton.developer import ScaffoldEngine, Wizard
    engine = ScaffoldEngine()
    wizard = Wizard(engine)
"""

from skeleton.developer.scaffold import ScaffoldEngine, list_templates
from skeleton.developer.wizard import ProjectWizard, SubsystemExplorer
from skeleton.developer.commands import CommandRegistry

# ``Wizard`` was the documented package-level name even though the implementation
# has always been ``ProjectWizard``. Keep that public spelling as a compatibility
# alias while exporting the canonical class explicitly.
Wizard = ProjectWizard

__all__ = [
    "ScaffoldEngine",
    "list_templates",
    "ProjectWizard",
    "Wizard",
    "SubsystemExplorer",
    "CommandRegistry",
]
