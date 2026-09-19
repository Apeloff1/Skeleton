"""Core portable toolchain contracts for the shell execution plane.

Language/ecosystem packs are intentionally layered above this module so the
compiler and transactional bridge do not import the full toolchain catalog.
"""

from skeleton.shells.toolchains.catalog import ToolchainBindingError, ToolchainCatalog, ToolchainCatalogSnapshot
from skeleton.shells.toolchains.compiler import (
    CommandEnvironmentPolicySet,
    CompiledToolchain,
    ToolchainAuthorityPolicy,
    ToolchainCompileError,
    ToolchainCompilerLimits,
    compile_toolchain,
)
from skeleton.shells.toolchains.execution import (
    PreparedToolchainInvocation,
    ToolchainExecutionPlane,
    ToolchainExecutionResult,
    ToolchainInvocation,
    ToolchainInvocationError,
)
from skeleton.shells.toolchains.manifest import (
    AuthorityChange,
    AuthorityManifestDiff,
    ContractAuthorityRecord,
    ToolchainAuthorityManifest,
    authority_record,
    build_authority_manifest,
    diff_authority_manifests,
    require_no_authority_widening,
    verify_authority_manifest,
)
from skeleton.shells.toolchains.transactional import (
    ToolchainMutationPolicyRouter,
    TransactionalToolchainError,
    TransactionalToolchainExecutionPlane,
    TransactionalToolchainResult,
    zero_mutation_policy,
)
from skeleton.shells.toolchains.types import BoundToolchain, CommandEffect, CommandRisk, LogicalCommandContract

__all__ = [
    "AuthorityChange", "AuthorityManifestDiff", "BoundToolchain", "CommandEffect",
    "CommandEnvironmentPolicySet", "CommandRisk", "CompiledToolchain",
    "ContractAuthorityRecord", "LogicalCommandContract", "PreparedToolchainInvocation",
    "ToolchainAuthorityManifest", "ToolchainAuthorityPolicy", "ToolchainBindingError",
    "ToolchainCatalog", "ToolchainCatalogSnapshot", "ToolchainCompileError",
    "ToolchainCompilerLimits", "ToolchainExecutionPlane", "ToolchainExecutionResult",
    "ToolchainInvocation", "ToolchainInvocationError", "ToolchainMutationPolicyRouter",
    "TransactionalToolchainError", "TransactionalToolchainExecutionPlane",
    "TransactionalToolchainResult", "authority_record", "build_authority_manifest",
    "compile_toolchain", "diff_authority_manifests", "require_no_authority_widening",
    "verify_authority_manifest", "zero_mutation_policy",
]
