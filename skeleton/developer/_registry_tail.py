# Global registry instance — with persistence commands
from skeleton.developer.persistence_commands import (
    RestoreCommand,
    SnapshotCommand,
    SnapshotsCommand,
)

_dev_registry = DevCommandRegistry()
_dev_registry.register("scaffold", ScaffoldCommand())
_dev_registry.register("wizard", WizardCommand())
_dev_registry.register("health", HealthCommand())
_dev_registry.register("visualize", VisualizeCommand())
_dev_registry.register("extension", ExtensionCommand())
_dev_registry.register("snapshot", SnapshotCommand())
_dev_registry.register("restore", RestoreCommand())
_dev_registry.register("snapshots", SnapshotsCommand())


def run_dev_command(command: str, args: List[str]) -> Any:
    """Entry point for all dev subcommands."""
    return _dev_registry.run(command, args)
