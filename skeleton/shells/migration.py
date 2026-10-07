"""Plan and validate shell policy/catalog migrations before activation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skeleton.shells.commands import CommandCatalog
from skeleton.shells.runner import ShellPolicy


class MigrationRisk(str, Enum):
    SAFE = "safe"
    REVIEW = "review"
    BREAKING = "breaking"


@dataclass(frozen=True)
class MigrationChange:
    risk: MigrationRisk
    code: str
    subject: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "risk": self.risk.value,
            "code": self.code,
            "subject": self.subject,
            "message": self.message,
        }


@dataclass(frozen=True)
class MigrationPlan:
    changes: tuple[MigrationChange, ...]

    @property
    def breaking(self) -> int:
        return sum(item.risk is MigrationRisk.BREAKING for item in self.changes)

    @property
    def review(self) -> int:
        return sum(item.risk is MigrationRisk.REVIEW for item in self.changes)

    @property
    def safe(self) -> int:
        return sum(item.risk is MigrationRisk.SAFE for item in self.changes)

    @property
    def requires_review(self) -> bool:
        return self.breaking > 0 or self.review > 0

    def to_dict(self) -> dict[str, object]:
        return {
            "breaking": self.breaking,
            "review": self.review,
            "safe": self.safe,
            "requires_review": self.requires_review,
            "changes": [item.to_dict() for item in self.changes],
        }


class ShellMigrationPlanner:
    def compare_policy(self, old: ShellPolicy, new: ShellPolicy) -> MigrationPlan:
        changes: list[MigrationChange] = []

        old_commands = set(old.executables)
        new_commands = set(new.executables)
        for name in sorted(new_commands - old_commands):
            changes.append(
                MigrationChange(MigrationRisk.SAFE, "executable_added", name, "registered executable added")
            )
        for name in sorted(old_commands - new_commands):
            changes.append(
                MigrationChange(MigrationRisk.BREAKING, "executable_removed", name, "registered executable removed")
            )
        for name in sorted(old_commands & new_commands):
            if old.executables[name] != new.executables[name]:
                changes.append(
                    MigrationChange(MigrationRisk.REVIEW, "executable_changed", name, "registered executable path changed")
                )

        if new.max_timeout > old.max_timeout:
            changes.append(
                MigrationChange(MigrationRisk.REVIEW, "timeout_widened", "policy", "maximum timeout increased")
            )
        elif new.max_timeout < old.max_timeout:
            changes.append(
                MigrationChange(MigrationRisk.SAFE, "timeout_narrowed", "policy", "maximum timeout decreased")
            )

        if new.max_output_bytes > old.max_output_bytes:
            changes.append(
                MigrationChange(MigrationRisk.REVIEW, "output_widened", "policy", "output byte limit increased")
            )
        elif new.max_output_bytes < old.max_output_bytes:
            changes.append(
                MigrationChange(MigrationRisk.SAFE, "output_narrowed", "policy", "output byte limit decreased")
            )

        added_env = set(new.allowed_env) - set(old.allowed_env)
        removed_env = set(old.allowed_env) - set(new.allowed_env)
        for key in sorted(added_env):
            changes.append(
                MigrationChange(MigrationRisk.REVIEW, "environment_added", key, "environment key added to allowlist")
            )
        for key in sorted(removed_env):
            changes.append(
                MigrationChange(MigrationRisk.BREAKING, "environment_removed", key, "environment key removed from allowlist")
            )

        if set(new.inherited_env) - set(old.inherited_env):
            changes.append(
                MigrationChange(MigrationRisk.REVIEW, "inheritance_widened", "environment", "parent environment inheritance widened")
            )
        if set(old.inherited_env) - set(new.inherited_env):
            changes.append(
                MigrationChange(MigrationRisk.SAFE, "inheritance_narrowed", "environment", "parent environment inheritance narrowed")
            )

        old_roots = {str(path) for path in old.cwd_roots}
        new_roots = {str(path) for path in new.cwd_roots}
        if new_roots - old_roots:
            changes.append(
                MigrationChange(MigrationRisk.REVIEW, "workspace_widened", "cwd_roots", "new working-directory roots added")
            )
        if old_roots - new_roots:
            changes.append(
                MigrationChange(MigrationRisk.BREAKING, "workspace_narrowed", "cwd_roots", "working-directory roots removed")
            )

        return MigrationPlan(tuple(changes))

    def compare_catalog(self, old: CommandCatalog, new: CommandCatalog) -> MigrationPlan:
        changes: list[MigrationChange] = []
        old_names = set(old.names())
        new_names = set(new.names())

        for name in sorted(new_names - old_names):
            changes.append(
                MigrationChange(MigrationRisk.SAFE, "command_added", name, "command contract added")
            )
        for name in sorted(old_names - new_names):
            changes.append(
                MigrationChange(MigrationRisk.BREAKING, "command_removed", name, "command contract removed")
            )

        for name in sorted(old_names & new_names):
            before = old.get(name)
            after = new.get(name)
            if before.to_dict() != after.to_dict():
                risk = MigrationRisk.REVIEW
                if before.allow_stdin and not after.allow_stdin:
                    risk = MigrationRisk.BREAKING
                if before.allow_nonzero_success and not after.allow_nonzero_success:
                    risk = MigrationRisk.BREAKING
                changes.append(
                    MigrationChange(risk, "command_changed", name, "command contract changed")
                )
        return MigrationPlan(tuple(changes))
