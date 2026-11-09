"""Explain authority changes between shell policies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from skeleton.shells.policy import is_narrower_or_equal
from skeleton.shells.runner import ShellPolicy


@dataclass(frozen=True)
class PolicyChange:
    field: str
    change: str
    authority: str
    detail: str

    def to_dict(self) -> dict[str, str]:
        return {
            "field": self.field,
            "change": self.change,
            "authority": self.authority,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class PolicyDiff:
    changes: tuple[PolicyChange, ...]
    wider: bool
    narrower_or_equal: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "wider": self.wider,
            "narrower_or_equal": self.narrower_or_equal,
            "changes": [change.to_dict() for change in self.changes],
        }


def diff_policies(before: ShellPolicy, after: ShellPolicy) -> PolicyDiff:
    changes: list[PolicyChange] = []
    before_exec = set(before.executables)
    after_exec = set(after.executables)
    for name in sorted(after_exec - before_exec):
        changes.append(PolicyChange("executables", "added", "wider", f"added executable {name}"))
    for name in sorted(before_exec - after_exec):
        changes.append(PolicyChange("executables", "removed", "narrower", f"removed executable {name}"))
    for name in sorted(before_exec & after_exec):
        if before.executables[name] != after.executables[name]:
            changes.append(PolicyChange("executables", "changed", "wider", f"changed executable target for {name}"))

    for key in sorted(after.allowed_env - before.allowed_env):
        changes.append(PolicyChange("allowed_env", "added", "wider", f"allowed environment key {key}"))
    for key in sorted(before.allowed_env - after.allowed_env):
        changes.append(PolicyChange("allowed_env", "removed", "narrower", f"removed environment key {key}"))
    for key in sorted(after.inherited_env - before.inherited_env):
        changes.append(PolicyChange("inherited_env", "added", "wider", f"inherited environment key {key}"))
    for key in sorted(before.inherited_env - after.inherited_env):
        changes.append(PolicyChange("inherited_env", "removed", "narrower", f"stopped inheriting environment key {key}"))

    limit_fields = (
        "max_timeout",
        "max_output_bytes",
        "max_input_bytes",
        "max_env_bytes",
        "max_args",
        "max_arg_bytes",
    )
    for field in limit_fields:
        old = getattr(before, field)
        new = getattr(after, field)
        if new == old:
            continue
        authority = "wider" if new > old else "narrower"
        changes.append(PolicyChange(field, "increased" if new > old else "decreased", authority, f"{old} -> {new}"))

    before_roots = tuple(Path(root) for root in before.cwd_roots)
    after_roots = tuple(Path(root) for root in after.cwd_roots)
    if before_roots != after_roots:
        root_wider = any(
            not any(candidate == parent or parent in candidate.parents for parent in before_roots)
            for candidate in after_roots
        )
        changes.append(
            PolicyChange(
                "cwd_roots",
                "changed",
                "wider" if root_wider else "narrower",
                f"cwd root set changed from {len(before_roots)} to {len(after_roots)} roots",
            )
        )

    wider = any(change.authority == "wider" for change in changes)
    return PolicyDiff(tuple(changes), wider=wider, narrower_or_equal=is_narrower_or_equal(after, before))
