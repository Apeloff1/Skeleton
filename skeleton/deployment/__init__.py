"""Compatibility namespace for deployment strategies.

New code should import from :mod:`skeleton.deploy.strategies`.
"""

from skeleton.deploy.strategies import (
    BlueGreenDeployer,
    CanaryController,
    EnvironmentManager,
    ReleaseNotesGenerator,
)

__all__ = [
    "BlueGreenDeployer",
    "CanaryController",
    "EnvironmentManager",
    "ReleaseNotesGenerator",
]
