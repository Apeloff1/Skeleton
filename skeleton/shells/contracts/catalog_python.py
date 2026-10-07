"""Python ecosystem typed shell command contracts."""

from __future__ import annotations

from skeleton.shells.contracts.core import CommandContract, FlagSpec, RiskTier, ToolEffect, VerbContract


def python_contract() -> CommandContract:
    """Python interpreter entrypoints"""
    return CommandContract(
        logical_name="python",
        description="Python interpreter entrypoints",
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
                            "-B": FlagSpec("-B", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-I": FlagSpec("-I", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-S": FlagSpec("-S", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-u": FlagSpec("-u", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-m": FlagSpec("-m", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-c": FlagSpec("-c", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def pytest_contract() -> CommandContract:
    """Pytest test runner"""
    return CommandContract(
        logical_name="pytest",
        description="Pytest test runner",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.READ, ToolEffect.PROCESS, ToolEffect.TEST}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-q": FlagSpec("-q", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-v": FlagSpec("-v", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-x": FlagSpec("-x", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--maxfail": FlagSpec("--maxfail", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-k": FlagSpec("-k", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-m": FlagSpec("-m", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--lf": FlagSpec("--lf", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--ff": FlagSpec("--ff", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--tb": FlagSpec("--tb", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def ruff_contract() -> CommandContract:
    """Ruff lint/format tool"""
    return CommandContract(
        logical_name="ruff",
        description="Ruff lint/format tool",
        default_verb=None,
        verbs={
            "check": VerbContract(
                name="check",
                effects=frozenset({ToolEffect.READ, ToolEffect.TEST}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--fix": FlagSpec("--fix", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--diff": FlagSpec("--diff", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--select": FlagSpec("--select", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--ignore": FlagSpec("--ignore", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--output-format": FlagSpec("--output-format", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "format": VerbContract(
                name="format",
                effects=frozenset({ToolEffect.WRITE}),
                risk=RiskTier.MEDIUM,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--check": FlagSpec("--check", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--diff": FlagSpec("--diff", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def mypy_contract() -> CommandContract:
    """Mypy type checker"""
    return CommandContract(
        logical_name="mypy",
        description="Mypy type checker",
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
                            "--strict": FlagSpec("--strict", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--check-untyped-defs": FlagSpec("--check-untyped-defs", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--ignore-missing-imports": FlagSpec("--ignore-missing-imports", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--config-file": FlagSpec("--config-file", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def uv_contract() -> CommandContract:
    """uv package/project manager"""
    return CommandContract(
        logical_name="uv",
        description="uv package/project manager",
        default_verb=None,
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
                            "--locked": FlagSpec("--locked", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--frozen": FlagSpec("--frozen", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--offline": FlagSpec("--offline", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "sync": VerbContract(
                name="sync",
                effects=frozenset({ToolEffect.PACKAGE, ToolEffect.WRITE, ToolEffect.NETWORK}),
                risk=RiskTier.HIGH,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--locked": FlagSpec("--locked", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--frozen": FlagSpec("--frozen", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--offline": FlagSpec("--offline", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "lock": VerbContract(
                name="lock",
                effects=frozenset({ToolEffect.PACKAGE, ToolEffect.WRITE, ToolEffect.NETWORK}),
                risk=RiskTier.HIGH,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--offline": FlagSpec("--offline", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "pip": VerbContract(
                name="pip",
                effects=frozenset({ToolEffect.PACKAGE, ToolEffect.NETWORK, ToolEffect.WRITE}),
                risk=RiskTier.HIGH,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--offline": FlagSpec("--offline", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--index-url": FlagSpec("--index-url", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def pip_contract() -> CommandContract:
    """pip package manager"""
    return CommandContract(
        logical_name="pip",
        description="pip package manager",
        default_verb=None,
        verbs={
            "list": VerbContract(
                name="list",
                effects=frozenset({ToolEffect.READ, ToolEffect.PACKAGE}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=0,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--format": FlagSpec("--format", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "show": VerbContract(
                name="show",
                effects=frozenset({ToolEffect.READ, ToolEffect.PACKAGE}),
                risk=RiskTier.LOW,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={},
            ),
            "check": VerbContract(
                name="check",
                effects=frozenset({ToolEffect.READ, ToolEffect.PACKAGE}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=0,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={},
            ),
            "install": VerbContract(
                name="install",
                effects=frozenset({ToolEffect.PACKAGE, ToolEffect.NETWORK, ToolEffect.WRITE}),
                risk=RiskTier.HIGH,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "-r": FlagSpec("-r", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--no-deps": FlagSpec("--no-deps", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--require-hashes": FlagSpec("--require-hashes", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "uninstall": VerbContract(
                name="uninstall",
                effects=frozenset({ToolEffect.PACKAGE, ToolEffect.WRITE, ToolEffect.DESTRUCTIVE}),
                risk=RiskTier.HIGH,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "-y": FlagSpec("-y", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def coverage_contract() -> CommandContract:
    """Coverage.py operations"""
    return CommandContract(
        logical_name="coverage",
        description="Coverage.py operations",
        default_verb=None,
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.READ, ToolEffect.PROCESS, ToolEffect.TEST}),
                risk=RiskTier.LOW,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-m": FlagSpec("-m", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--branch": FlagSpec("--branch", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "report": VerbContract(
                name="report",
                effects=frozenset({ToolEffect.READ, ToolEffect.TEST}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-m": FlagSpec("-m", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--fail-under": FlagSpec("--fail-under", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "xml": VerbContract(
                name="xml",
                effects=frozenset({ToolEffect.WRITE, ToolEffect.TEST}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-o": FlagSpec("-o", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "html": VerbContract(
                name="html",
                effects=frozenset({ToolEffect.WRITE, ToolEffect.TEST}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-d": FlagSpec("-d", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


CONTRACT_FACTORIES = (
    python_contract,
    pytest_contract,
    ruff_contract,
    mypy_contract,
    uv_contract,
    pip_contract,
    coverage_contract,
)


def contracts() -> tuple[CommandContract, ...]:
    return tuple(factory() for factory in CONTRACT_FACTORIES)
