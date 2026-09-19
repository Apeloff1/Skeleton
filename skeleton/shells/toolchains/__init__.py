"""Built-in portable toolchain contracts for the shell execution plane."""

from skeleton.shells.toolchains.all import ALL_CONTRACTS, DEFAULT_CATALOG, all_contracts, default_catalog
from skeleton.shells.toolchains.catalog import ToolchainBindingError, ToolchainCatalog, ToolchainCatalogSnapshot
from skeleton.shells.toolchains.profiles import ContractProfile, PROFILES, profile
from skeleton.shells.toolchains.recipes import DEFAULT_RECIPES, RECIPES, RecipeCatalog, ToolchainRecipe, ToolchainStep
from skeleton.shells.toolchains.types import BoundToolchain, CommandEffect, CommandRisk, LogicalCommandContract

__all__ = [
    "ALL_CONTRACTS",
    "DEFAULT_CATALOG",
    "all_contracts",
    "default_catalog",
    "ToolchainBindingError",
    "ToolchainCatalog",
    "ToolchainCatalogSnapshot",
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
