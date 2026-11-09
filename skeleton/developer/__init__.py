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
from skeleton.developer.commands import DevCommandRegistry

# Keep the documented package-level compatibility names while exposing the
# canonical implementation classes explicitly.
Wizard = ProjectWizard
CommandRegistry = DevCommandRegistry

# ``CommandRegistry`` is the historical package-level spelling. The concrete
# implementation is ``DevCommandRegistry``; alias it here so importing
# ``skeleton.developer`` stays compatible without duplicating registry logic.
CommandRegistry = DevCommandRegistry

__all__ = [
    "ScaffoldEngine",
    "list_templates",
    "ProjectWizard",
    "Wizard",
    "SubsystemExplorer",
    "DevCommandRegistry",
    "CommandRegistry",
]
