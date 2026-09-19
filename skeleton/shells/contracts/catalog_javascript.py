"""JavaScript ecosystem typed shell command contracts."""

from __future__ import annotations

from skeleton.shells.contracts.core import CommandContract, FlagSpec, RiskTier, ToolEffect, VerbContract


def node_contract() -> CommandContract:
    """Node.js runtime"""
    return CommandContract(
        logical_name="node",
        description="Node.js runtime",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.PROCESS}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--check": FlagSpec("--check", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--test": FlagSpec("--test", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--input-type": FlagSpec("--input-type", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def npm_contract() -> CommandContract:
    """npm package manager"""
    return CommandContract(
        logical_name="npm",
        description="npm package manager",
        default_verb=None,
        verbs={
            "test": VerbContract(
                name="test",
                effects=frozenset({ToolEffect.READ, ToolEffect.PROCESS, ToolEffect.TEST}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={},
            ),
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.PROCESS}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--if-present": FlagSpec("--if-present", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "install": VerbContract(
                name="install",
                effects=frozenset({ToolEffect.PACKAGE, ToolEffect.NETWORK, ToolEffect.WRITE}),
                risk=RiskTier.HIGH,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--ignore-scripts": FlagSpec("--ignore-scripts", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--no-audit": FlagSpec("--no-audit", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--offline": FlagSpec("--offline", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "ci": VerbContract(
                name="ci",
                effects=frozenset({ToolEffect.PACKAGE, ToolEffect.NETWORK, ToolEffect.WRITE}),
                risk=RiskTier.HIGH,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--ignore-scripts": FlagSpec("--ignore-scripts", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--offline": FlagSpec("--offline", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "audit": VerbContract(
                name="audit",
                effects=frozenset({ToolEffect.NETWORK, ToolEffect.READ}),
                risk=RiskTier.MEDIUM,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--json": FlagSpec("--json", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def npx_contract() -> CommandContract:
    """npx package runner"""
    return CommandContract(
        logical_name="npx",
        description="npx package runner",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.PACKAGE, ToolEffect.NETWORK, ToolEffect.PROCESS}),
                risk=RiskTier.HIGH,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--yes": FlagSpec("--yes", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--no-install": FlagSpec("--no-install", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def pnpm_contract() -> CommandContract:
    """pnpm package manager"""
    return CommandContract(
        logical_name="pnpm",
        description="pnpm package manager",
        default_verb=None,
        verbs={
            "test": VerbContract(
                name="test",
                effects=frozenset({ToolEffect.READ, ToolEffect.PROCESS, ToolEffect.TEST}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={},
            ),
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.PROCESS}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={},
            ),
            "install": VerbContract(
                name="install",
                effects=frozenset({ToolEffect.PACKAGE, ToolEffect.NETWORK, ToolEffect.WRITE}),
                risk=RiskTier.HIGH,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--frozen-lockfile": FlagSpec("--frozen-lockfile", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--offline": FlagSpec("--offline", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--ignore-scripts": FlagSpec("--ignore-scripts", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def yarn_contract() -> CommandContract:
    """Yarn package manager"""
    return CommandContract(
        logical_name="yarn",
        description="Yarn package manager",
        default_verb=None,
        verbs={
            "test": VerbContract(
                name="test",
                effects=frozenset({ToolEffect.READ, ToolEffect.PROCESS, ToolEffect.TEST}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={},
            ),
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.PROCESS}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={},
            ),
            "install": VerbContract(
                name="install",
                effects=frozenset({ToolEffect.PACKAGE, ToolEffect.NETWORK, ToolEffect.WRITE}),
                risk=RiskTier.HIGH,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--immutable": FlagSpec("--immutable", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--offline": FlagSpec("--offline", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--ignore-scripts": FlagSpec("--ignore-scripts", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def eslint_contract() -> CommandContract:
    """ESLint checker"""
    return CommandContract(
        logical_name="eslint",
        description="ESLint checker",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.READ, ToolEffect.TEST}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--fix": FlagSpec("--fix", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--max-warnings": FlagSpec("--max-warnings", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--format": FlagSpec("--format", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def prettier_contract() -> CommandContract:
    """Prettier formatter"""
    return CommandContract(
        logical_name="prettier",
        description="Prettier formatter",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.READ}),
                risk=RiskTier.LOW,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--check": FlagSpec("--check", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--write": FlagSpec("--write", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--list-different": FlagSpec("--list-different", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def vite_contract() -> CommandContract:
    """Vite build tool"""
    return CommandContract(
        logical_name="vite",
        description="Vite build tool",
        default_verb=None,
        verbs={
            "build": VerbContract(
                name="build",
                effects=frozenset({ToolEffect.READ, ToolEffect.WRITE, ToolEffect.BUILD}),
                risk=RiskTier.MEDIUM,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--mode": FlagSpec("--mode", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--outDir": FlagSpec("--outDir", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "preview": VerbContract(
                name="preview",
                effects=frozenset({ToolEffect.PROCESS, ToolEffect.NETWORK}),
                risk=RiskTier.MEDIUM,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--host": FlagSpec("--host", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--port": FlagSpec("--port", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


CONTRACT_FACTORIES = (
    node_contract,
    npm_contract,
    npx_contract,
    pnpm_contract,
    yarn_contract,
    eslint_contract,
    prettier_contract,
    vite_contract,
)


def contracts() -> tuple[CommandContract, ...]:
    return tuple(factory() for factory in CONTRACT_FACTORIES)
