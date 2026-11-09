"""Read-oriented system typed shell command contracts."""

from __future__ import annotations

from skeleton.shells.contracts.core import CommandContract, FlagSpec, RiskTier, ToolEffect, VerbContract


def rg_contract() -> CommandContract:
    """ripgrep search"""
    return CommandContract(
        logical_name="rg",
        description="ripgrep search",
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
                            "-n": FlagSpec("-n", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-i": FlagSpec("-i", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-F": FlagSpec("-F", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-g": FlagSpec("-g", takes_value=True, repeatable=True, effects=frozenset({})),
                            "--glob": FlagSpec("--glob", takes_value=True, repeatable=True, effects=frozenset({})),
                            "--hidden": FlagSpec("--hidden", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--files": FlagSpec("--files", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def grep_contract() -> CommandContract:
    """grep search"""
    return CommandContract(
        logical_name="grep",
        description="grep search",
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
                            "-n": FlagSpec("-n", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-i": FlagSpec("-i", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-F": FlagSpec("-F", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-E": FlagSpec("-E", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-R": FlagSpec("-R", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--exclude": FlagSpec("--exclude", takes_value=True, repeatable=True, effects=frozenset({})),
                        },
            ),
        },
    )


def find_contract() -> CommandContract:
    """find filesystem query"""
    return CommandContract(
        logical_name="find",
        description="find filesystem query",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.READ}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-maxdepth": FlagSpec("-maxdepth", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-mindepth": FlagSpec("-mindepth", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-name": FlagSpec("-name", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-type": FlagSpec("-type", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def ls_contract() -> CommandContract:
    """directory listing"""
    return CommandContract(
        logical_name="ls",
        description="directory listing",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.READ}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-l": FlagSpec("-l", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-a": FlagSpec("-a", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-h": FlagSpec("-h", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-R": FlagSpec("-R", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def cat_contract() -> CommandContract:
    """file concatenation"""
    return CommandContract(
        logical_name="cat",
        description="file concatenation",
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
                            "-n": FlagSpec("-n", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-b": FlagSpec("-b", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def head_contract() -> CommandContract:
    """file prefix reader"""
    return CommandContract(
        logical_name="head",
        description="file prefix reader",
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
                            "-n": FlagSpec("-n", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-c": FlagSpec("-c", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def tail_contract() -> CommandContract:
    """file suffix reader"""
    return CommandContract(
        logical_name="tail",
        description="file suffix reader",
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
                            "-n": FlagSpec("-n", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-c": FlagSpec("-c", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def sort_contract() -> CommandContract:
    """sort text"""
    return CommandContract(
        logical_name="sort",
        description="sort text",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.READ}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-n": FlagSpec("-n", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-r": FlagSpec("-r", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-u": FlagSpec("-u", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-k": FlagSpec("-k", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def wc_contract() -> CommandContract:
    """count text"""
    return CommandContract(
        logical_name="wc",
        description="count text",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.READ}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-l": FlagSpec("-l", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-w": FlagSpec("-w", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-c": FlagSpec("-c", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def diff_contract() -> CommandContract:
    """compare files"""
    return CommandContract(
        logical_name="diff",
        description="compare files",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.READ}),
                risk=RiskTier.LOW,
                min_positionals=2,
                max_positionals=2,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-u": FlagSpec("-u", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-q": FlagSpec("-q", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--brief": FlagSpec("--brief", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


CONTRACT_FACTORIES = (
    rg_contract,
    grep_contract,
    find_contract,
    ls_contract,
    cat_contract,
    head_contract,
    tail_contract,
    sort_contract,
    wc_contract,
    diff_contract,
)


def contracts() -> tuple[CommandContract, ...]:
    return tuple(factory() for factory in CONTRACT_FACTORIES)
