"""Native build typed shell command contracts."""

from __future__ import annotations

from skeleton.shells.contracts.core import CommandContract, FlagSpec, RiskTier, ToolEffect, VerbContract


def cargo_contract() -> CommandContract:
    """Rust Cargo tool"""
    return CommandContract(
        logical_name="cargo",
        description="Rust Cargo tool",
        default_verb=None,
        verbs={
            "check": VerbContract(
                name="check",
                effects=frozenset({ToolEffect.READ, ToolEffect.BUILD}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--workspace": FlagSpec("--workspace", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--all-targets": FlagSpec("--all-targets", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--locked": FlagSpec("--locked", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--offline": FlagSpec("--offline", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "test": VerbContract(
                name="test",
                effects=frozenset({ToolEffect.READ, ToolEffect.BUILD, ToolEffect.TEST}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--workspace": FlagSpec("--workspace", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--all-targets": FlagSpec("--all-targets", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--locked": FlagSpec("--locked", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--offline": FlagSpec("--offline", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "build": VerbContract(
                name="build",
                effects=frozenset({ToolEffect.READ, ToolEffect.WRITE, ToolEffect.BUILD}),
                risk=RiskTier.MEDIUM,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--release": FlagSpec("--release", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--workspace": FlagSpec("--workspace", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--locked": FlagSpec("--locked", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--offline": FlagSpec("--offline", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "fmt": VerbContract(
                name="fmt",
                effects=frozenset({ToolEffect.READ, ToolEffect.WRITE}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--check": FlagSpec("--check", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "clippy": VerbContract(
                name="clippy",
                effects=frozenset({ToolEffect.READ, ToolEffect.BUILD, ToolEffect.TEST}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--workspace": FlagSpec("--workspace", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--all-targets": FlagSpec("--all-targets", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
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
                            "--locked": FlagSpec("--locked", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--offline": FlagSpec("--offline", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def rustc_contract() -> CommandContract:
    """Rust compiler"""
    return CommandContract(
        logical_name="rustc",
        description="Rust compiler",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.READ, ToolEffect.WRITE, ToolEffect.BUILD}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--edition": FlagSpec("--edition", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--crate-type": FlagSpec("--crate-type", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-o": FlagSpec("-o", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def go_contract() -> CommandContract:
    """Go toolchain"""
    return CommandContract(
        logical_name="go",
        description="Go toolchain",
        default_verb=None,
        verbs={
            "test": VerbContract(
                name="test",
                effects=frozenset({ToolEffect.READ, ToolEffect.BUILD, ToolEffect.TEST}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-race": FlagSpec("-race", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-count": FlagSpec("-count", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-run": FlagSpec("-run", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "build": VerbContract(
                name="build",
                effects=frozenset({ToolEffect.READ, ToolEffect.WRITE, ToolEffect.BUILD}),
                risk=RiskTier.MEDIUM,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-o": FlagSpec("-o", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-race": FlagSpec("-race", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "fmt": VerbContract(
                name="fmt",
                effects=frozenset({ToolEffect.READ, ToolEffect.WRITE}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={},
            ),
            "vet": VerbContract(
                name="vet",
                effects=frozenset({ToolEffect.READ, ToolEffect.TEST}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={},
            ),
            "mod": VerbContract(
                name="mod",
                effects=frozenset({ToolEffect.NETWORK, ToolEffect.PACKAGE, ToolEffect.WRITE}),
                risk=RiskTier.HIGH,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={},
            ),
        },
    )


def make_contract() -> CommandContract:
    """Make build driver"""
    return CommandContract(
        logical_name="make",
        description="Make build driver",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.READ, ToolEffect.WRITE, ToolEffect.BUILD, ToolEffect.PROCESS}),
                risk=RiskTier.MEDIUM,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-j": FlagSpec("-j", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-n": FlagSpec("-n", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-C": FlagSpec("-C", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def cmake_contract() -> CommandContract:
    """CMake generator"""
    return CommandContract(
        logical_name="cmake",
        description="CMake generator",
        default_verb=None,
        verbs={
            "configure": VerbContract(
                name="configure",
                effects=frozenset({ToolEffect.READ, ToolEffect.WRITE, ToolEffect.BUILD}),
                risk=RiskTier.MEDIUM,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-S": FlagSpec("-S", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-B": FlagSpec("-B", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-G": FlagSpec("-G", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "build": VerbContract(
                name="build",
                effects=frozenset({ToolEffect.READ, ToolEffect.WRITE, ToolEffect.BUILD, ToolEffect.PROCESS}),
                risk=RiskTier.MEDIUM,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--build": FlagSpec("--build", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--parallel": FlagSpec("--parallel", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--target": FlagSpec("--target", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def ninja_contract() -> CommandContract:
    """Ninja build driver"""
    return CommandContract(
        logical_name="ninja",
        description="Ninja build driver",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.READ, ToolEffect.WRITE, ToolEffect.BUILD, ToolEffect.PROCESS}),
                risk=RiskTier.MEDIUM,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-j": FlagSpec("-j", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-n": FlagSpec("-n", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-C": FlagSpec("-C", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def gcc_contract() -> CommandContract:
    """GNU C compiler"""
    return CommandContract(
        logical_name="gcc",
        description="GNU C compiler",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.READ, ToolEffect.WRITE, ToolEffect.BUILD}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-c": FlagSpec("-c", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-o": FlagSpec("-o", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-I": FlagSpec("-I", takes_value=True, repeatable=True, effects=frozenset({})),
                            "-D": FlagSpec("-D", takes_value=True, repeatable=True, effects=frozenset({})),
                            "-Wall": FlagSpec("-Wall", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-Wextra": FlagSpec("-Wextra", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def clang_contract() -> CommandContract:
    """Clang compiler"""
    return CommandContract(
        logical_name="clang",
        description="Clang compiler",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.READ, ToolEffect.WRITE, ToolEffect.BUILD}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-c": FlagSpec("-c", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-o": FlagSpec("-o", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-I": FlagSpec("-I", takes_value=True, repeatable=True, effects=frozenset({})),
                            "-D": FlagSpec("-D", takes_value=True, repeatable=True, effects=frozenset({})),
                            "-Wall": FlagSpec("-Wall", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-Wextra": FlagSpec("-Wextra", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


CONTRACT_FACTORIES = (
    cargo_contract,
    rustc_contract,
    go_contract,
    make_contract,
    cmake_contract,
    ninja_contract,
    gcc_contract,
    clang_contract,
)


def contracts() -> tuple[CommandContract, ...]:
    return tuple(factory() for factory in CONTRACT_FACTORIES)
