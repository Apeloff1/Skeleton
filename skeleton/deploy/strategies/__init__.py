"""Canonical deployment strategy implementations.

Compatibility imports remain available under `skeleton.deployment` while
callers migrate to this namespace.
"""

from .blue_green import BlueGreenDeployer
from .canary import CanaryController
from .environment_manager import EnvironmentManager
from .release_notes import ReleaseNotesGenerator

__all__ = [
    "BlueGreenDeployer",
    "CanaryController",
    "EnvironmentManager",
    "ReleaseNotesGenerator",
]
