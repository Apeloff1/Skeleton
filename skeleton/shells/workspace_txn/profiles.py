"""Named operational workspace transaction profiles."""

from __future__ import annotations

from skeleton.shells.workspace_txn.builtin_rules import standard_rules
from skeleton.shells.workspace_txn.policy import WorkspaceMutationPolicy
from skeleton.shells.workspace_txn.rules import MaxBytesRule, MaxChangesRule, MaxDepthRule, MaxFileSizeRule, SymlinkMutationRule

def tiny_patch_policy() -> WorkspaceMutationPolicy:
    """Build the tiny patch transaction profile."""
    return WorkspaceMutationPolicy(
        name="tiny_patch",
        fail_on_warning=True,
        rules=(
            MaxChangesRule(64),
            MaxBytesRule(added=8388608, removed=8388608),
            MaxFileSizeRule(16777216),
            MaxDepthRule(16),
            SymlinkMutationRule(False, False, False),
            *standard_rules(),
        ),
        metadata={"profile_class": "workspace-transaction", "profile_name": "tiny_patch"},
    )


def source_patch_policy() -> WorkspaceMutationPolicy:
    """Build the source patch transaction profile."""
    return WorkspaceMutationPolicy(
        name="source_patch",
        fail_on_warning=False,
        rules=(
            MaxChangesRule(2500),
            MaxBytesRule(added=134217728, removed=134217728),
            MaxFileSizeRule(67108864),
            MaxDepthRule(48),
            SymlinkMutationRule(False, False, False),
            *standard_rules(),
        ),
        metadata={"profile_class": "workspace-transaction", "profile_name": "source_patch"},
    )


def large_refactor_policy() -> WorkspaceMutationPolicy:
    """Build the large refactor transaction profile."""
    return WorkspaceMutationPolicy(
        name="large_refactor",
        fail_on_warning=False,
        rules=(
            MaxChangesRule(25000),
            MaxBytesRule(added=1073741824, removed=1073741824),
            MaxFileSizeRule(268435456),
            MaxDepthRule(72),
            SymlinkMutationRule(False, False, False),
            *standard_rules(),
        ),
        metadata={"profile_class": "workspace-transaction", "profile_name": "large_refactor"},
    )


def generated_code_policy() -> WorkspaceMutationPolicy:
    """Build the generated code transaction profile."""
    return WorkspaceMutationPolicy(
        name="generated_code",
        fail_on_warning=False,
        rules=(
            MaxChangesRule(100000),
            MaxBytesRule(added=4294967296, removed=4294967296),
            MaxFileSizeRule(536870912),
            MaxDepthRule(96),
            SymlinkMutationRule(False, False, False),
            *standard_rules(),
        ),
        metadata={"profile_class": "workspace-transaction", "profile_name": "generated_code"},
    )


def docs_only_policy() -> WorkspaceMutationPolicy:
    """Build the docs only transaction profile."""
    return WorkspaceMutationPolicy(
        name="docs_only",
        fail_on_warning=False,
        rules=(
            MaxChangesRule(10000),
            MaxBytesRule(added=536870912, removed=268435456),
            MaxFileSizeRule(67108864),
            MaxDepthRule(64),
            SymlinkMutationRule(False, False, False),
            *standard_rules(),
        ),
        metadata={"profile_class": "workspace-transaction", "profile_name": "docs_only"},
    )


def migration_policy() -> WorkspaceMutationPolicy:
    """Build the migration transaction profile."""
    return WorkspaceMutationPolicy(
        name="migration",
        fail_on_warning=False,
        rules=(
            MaxChangesRule(50000),
            MaxBytesRule(added=2147483648, removed=2147483648),
            MaxFileSizeRule(268435456),
            MaxDepthRule(96),
            SymlinkMutationRule(False, False, False),
            *standard_rules(),
        ),
        metadata={"profile_class": "workspace-transaction", "profile_name": "migration"},
    )


def maintenance_policy() -> WorkspaceMutationPolicy:
    """Build the maintenance transaction profile."""
    return WorkspaceMutationPolicy(
        name="maintenance",
        fail_on_warning=False,
        rules=(
            MaxChangesRule(20000),
            MaxBytesRule(added=1073741824, removed=1073741824),
            MaxFileSizeRule(268435456),
            MaxDepthRule(80),
            SymlinkMutationRule(False, False, False),
            *standard_rules(),
        ),
        metadata={"profile_class": "workspace-transaction", "profile_name": "maintenance"},
    )


def strict_ci_fix_policy() -> WorkspaceMutationPolicy:
    """Build the strict ci fix transaction profile."""
    return WorkspaceMutationPolicy(
        name="strict_ci_fix",
        fail_on_warning=True,
        rules=(
            MaxChangesRule(512),
            MaxBytesRule(added=67108864, removed=67108864),
            MaxFileSizeRule(33554432),
            MaxDepthRule(40),
            SymlinkMutationRule(False, False, False),
            *standard_rules(),
        ),
        metadata={"profile_class": "workspace-transaction", "profile_name": "strict_ci_fix"},
    )


def test_generation_policy() -> WorkspaceMutationPolicy:
    """Build the test generation transaction profile."""
    return WorkspaceMutationPolicy(
        name="test_generation",
        fail_on_warning=False,
        rules=(
            MaxChangesRule(30000),
            MaxBytesRule(added=536870912, removed=268435456),
            MaxFileSizeRule(33554432),
            MaxDepthRule(72),
            SymlinkMutationRule(False, False, False),
            *standard_rules(),
        ),
        metadata={"profile_class": "workspace-transaction", "profile_name": "test_generation"},
    )


def documentation_policy() -> WorkspaceMutationPolicy:
    """Build the documentation transaction profile."""
    return WorkspaceMutationPolicy(
        name="documentation",
        fail_on_warning=False,
        rules=(
            MaxChangesRule(12000),
            MaxBytesRule(added=268435456, removed=134217728),
            MaxFileSizeRule(33554432),
            MaxDepthRule(64),
            SymlinkMutationRule(False, False, False),
            *standard_rules(),
        ),
        metadata={"profile_class": "workspace-transaction", "profile_name": "documentation"},
    )


PROFILE_FACTORIES = {
    "tiny_patch": tiny_patch_policy,
    "source_patch": source_patch_policy,
    "large_refactor": large_refactor_policy,
    "generated_code": generated_code_policy,
    "docs_only": docs_only_policy,
    "migration": migration_policy,
    "maintenance": maintenance_policy,
    "strict_ci_fix": strict_ci_fix_policy,
    "test_generation": test_generation_policy,
    "documentation": documentation_policy,
}


def build_profile(name: str) -> WorkspaceMutationPolicy:
    try:
        factory = PROFILE_FACTORIES[name]
    except KeyError as exc:
        raise KeyError(f"unknown workspace transaction profile: {name}") from exc
    return factory()
