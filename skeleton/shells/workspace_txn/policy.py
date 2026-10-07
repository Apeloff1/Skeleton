"""Workspace mutation policy composition and standard profiles."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from typing import Iterable

from skeleton.shells.provenance import canonical_json
from skeleton.shells.workspace_txn.pathing import PathMatcher
from skeleton.shells.workspace_txn.rules import (
    DeleteRule,
    ExecutableBitRule,
    ExtensionDenyRule,
    FilenameDenyRule,
    MaxBytesRule,
    MaxChangesRule,
    MaxDepthRule,
    MaxFileSizeRule,
    MaxKindRule,
    MutationRule,
    PathDenyRule,
    RegexPathDenyRule,
    SymlinkMutationRule,
    evaluate_rules,
)
from skeleton.shells.workspace_txn.types import ChangeSet, MutationDecision, WorkspaceChangeKind


@dataclass(frozen=True)
class WorkspaceMutationPolicy:
    rules: tuple[MutationRule, ...]
    name: str = "custom"
    fail_on_warning: bool = False
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "rules", tuple(self.rules))
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def digest(self) -> str:
        payload = {
            "name": self.name,
            "fail_on_warning": self.fail_on_warning,
            "metadata": dict(sorted(self.metadata.items())),
            "rules": [rule.to_dict() for rule in self.rules],
        }
        return hashlib.sha256(canonical_json(payload)).hexdigest()

    def evaluate(self, changes: ChangeSet) -> MutationDecision:
        violations = evaluate_rules(self.rules, changes)
        blocking = any(v.severity in {"error", "critical"} for v in violations)
        if self.fail_on_warning:
            blocking = blocking or any(v.severity == "warning" for v in violations)
        return MutationDecision(not blocking, violations, changes.digest, self.digest)

    def extend(self, *rules: MutationRule, name: str | None = None) -> "WorkspaceMutationPolicy":
        return WorkspaceMutationPolicy(
            self.rules + tuple(rules),
            name=name or self.name,
            fail_on_warning=self.fail_on_warning,
            metadata=self.metadata,
        )


def protected_repository_rule() -> PathDenyRule:
    return PathDenyRule(
        PathMatcher(
            include=(
                ".git/**",
                ".github/workflows/**",
                ".github/actions/**",
                ".env",
                ".env.*",
                "**/.env",
                "**/.env.*",
                "**/*secret*",
                "**/*credential*",
                "**/*token*",
                "**/id_rsa",
                "**/id_ed25519",
            )
        )
    )


def default_safe_policy() -> WorkspaceMutationPolicy:
    return WorkspaceMutationPolicy(
        name="safe-default",
        rules=(
            MaxChangesRule(20_000),
            MaxKindRule(WorkspaceChangeKind.DELETED, 2_000, code="max_deleted"),
            MaxKindRule(WorkspaceChangeKind.RENAMED, 5_000, code="max_renamed"),
            MaxBytesRule(added=512 * 1024 * 1024, removed=512 * 1024 * 1024),
            MaxFileSizeRule(128 * 1024 * 1024),
            MaxDepthRule(64),
            protected_repository_rule(),
            ExtensionDenyRule(frozenset({".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".der"})),
            FilenameDenyRule(
                frozenset(
                    {
                        ".netrc",
                        ".npmrc",
                        ".pypirc",
                        "credentials",
                        "credentials.json",
                        "secrets.json",
                        "authorized_keys",
                        "known_hosts",
                    }
                )
            ),
            RegexPathDenyRule(
                (
                    r"(^|/)node_modules(/|$)",
                    r"(^|/)__pycache__(/|$)",
                    r"(^|/)\.venv(/|$)",
                    r"(^|/)venv(/|$)",
                ),
                code="generated_tree_denied",
            ),
            SymlinkMutationRule(False, False, False),
            ExecutableBitRule(False, True),
        ),
    )


def source_edit_policy() -> WorkspaceMutationPolicy:
    return default_safe_policy().extend(
        DeleteRule(
            allow=True,
            matcher=PathMatcher(
                include=(
                    "pyproject.toml",
                    "package-lock.json",
                    "pnpm-lock.yaml",
                    "yarn.lock",
                    "uv.lock",
                    "Cargo.lock",
                )
            ),
            code="lockfile_delete_denied",
        ),
        name="source-edit",
    )


def generated_output_policy() -> WorkspaceMutationPolicy:
    return WorkspaceMutationPolicy(
        name="generated-output",
        rules=(
            MaxChangesRule(100_000),
            MaxBytesRule(added=2 * 1024 * 1024 * 1024, removed=2 * 1024 * 1024 * 1024),
            MaxFileSizeRule(512 * 1024 * 1024),
            MaxDepthRule(96),
            protected_repository_rule(),
            SymlinkMutationRule(False, False, False),
        ),
    )


class PolicyCatalog:
    def __init__(self, policies: Iterable[WorkspaceMutationPolicy] = ()) -> None:
        self._policies: dict[str, WorkspaceMutationPolicy] = {}
        for policy in policies:
            self.register(policy)

    @classmethod
    def defaults(cls) -> "PolicyCatalog":
        return cls((default_safe_policy(), source_edit_policy(), generated_output_policy()))

    def register(self, policy: WorkspaceMutationPolicy, *, replace: bool = False) -> None:
        if policy.name in self._policies and not replace:
            raise ValueError(f"workspace policy already registered: {policy.name}")
        self._policies[policy.name] = policy

    def get(self, name: str) -> WorkspaceMutationPolicy:
        try:
            return self._policies[name]
        except KeyError as exc:
            raise KeyError(f"unknown workspace policy: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._policies))
