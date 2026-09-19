"""Built-in portable toolchain contracts for the shell execution plane."""

from skeleton.shells.toolchains.all import ALL_CONTRACTS, DEFAULT_CATALOG, all_contracts, default_catalog
from skeleton.shells.toolchains.attestation import (
    AttestedToolchainExecutionPlane,
    ExecutableAttestation,
    ExecutableAttestationError,
    ExecutableAttestationPolicy,
    ExecutableAttestationSet,
    ExecutableAttestor,
    ExecutableVerification,
    attest_compiled_toolchain,
)
from skeleton.shells.toolchains.catalog import ToolchainBindingError, ToolchainCatalog, ToolchainCatalogSnapshot
from skeleton.shells.toolchains.compiler import (
    CommandEnvironmentPolicySet,
    CompiledToolchain,
    ToolchainAuthorityPolicy,
    ToolchainCompileError,
    ToolchainCompilerLimits,
    compile_toolchain,
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
from skeleton.shells.toolchains.execution import (
    PreparedToolchainInvocation,
    ToolchainExecutionPlane,
    ToolchainExecutionResult,
    ToolchainInvocation,
    ToolchainInvocationError,
)
from skeleton.shells.toolchains.profiles import ContractProfile, PROFILES, profile
from skeleton.shells.toolchains.recipes import DEFAULT_RECIPES, RECIPES, RecipeCatalog, ToolchainRecipe, ToolchainStep
from skeleton.shells.toolchains.types import BoundToolchain, CommandEffect, CommandRisk, LogicalCommandContract

__all__ = [
    "ALL_CONTRACTS",
    "DEFAULT_CATALOG",
    "AttestedToolchainExecutionPlane",
    "ExecutableAttestation",
    "ExecutableAttestationError",
    "ExecutableAttestationPolicy",
    "ExecutableAttestationSet",
    "ExecutableAttestor",
    "ExecutableVerification",
    "attest_compiled_toolchain",
    "all_contracts",
    "default_catalog",
    "ToolchainBindingError",
    "ToolchainCatalog",
    "ToolchainCatalogSnapshot",
    "CommandEnvironmentPolicySet",
    "CompiledToolchain",
    "ToolchainAuthorityPolicy",
    "ToolchainCompileError",
    "ToolchainCompilerLimits",
    "compile_toolchain",
    "PreparedToolchainInvocation",
    "ToolchainExecutionPlane",
    "ToolchainExecutionResult",
    "ToolchainInvocation",
    "ToolchainInvocationError",
    "AuthorityChange",
    "AuthorityManifestDiff",
    "ContractAuthorityRecord",
    "ToolchainAuthorityManifest",
    "authority_record",
    "build_authority_manifest",
    "diff_authority_manifests",
    "require_no_authority_widening",
    "verify_authority_manifest",
    "ContractProfile",
    "PROFILES",
    "profile",
    "DEFAULT_RECIPES",
    "RECIPES",
    "RecipeCatalog",
    "ToolchainRecipe",
    "ToolchainStep",
    "BoundToolchain",
    "CommandEffect",
    "CommandRisk",
    "LogicalCommandContract",
]
