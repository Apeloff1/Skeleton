"""Data and archive typed shell command contracts."""

from __future__ import annotations

from skeleton.shells.contracts.core import CommandContract, FlagSpec, RiskTier, ToolEffect, VerbContract


def jq_contract() -> CommandContract:
    """JSON processor"""
    return CommandContract(
        logical_name="jq",
        description="JSON processor",
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
                            "-r": FlagSpec("-r", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-c": FlagSpec("-c", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-S": FlagSpec("-S", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--arg": FlagSpec("--arg", takes_value=True, repeatable=True, effects=frozenset({})),
                        },
            ),
        },
    )


def sqlite3_contract() -> CommandContract:
    """SQLite CLI"""
    return CommandContract(
        logical_name="sqlite3",
        description="SQLite CLI",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.READ, ToolEffect.WRITE}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-readonly": FlagSpec("-readonly", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-json": FlagSpec("-json", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-csv": FlagSpec("-csv", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-header": FlagSpec("-header", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def tar_contract() -> CommandContract:
    """tar archive tool"""
    return CommandContract(
        logical_name="tar",
        description="tar archive tool",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.READ, ToolEffect.WRITE, ToolEffect.ARCHIVE}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-c": FlagSpec("-c", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-x": FlagSpec("-x", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-t": FlagSpec("-t", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-f": FlagSpec("-f", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-C": FlagSpec("-C", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--strip-components": FlagSpec("--strip-components", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def zip_contract() -> CommandContract:
    """zip archive tool"""
    return CommandContract(
        logical_name="zip",
        description="zip archive tool",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.READ, ToolEffect.WRITE, ToolEffect.ARCHIVE}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-r": FlagSpec("-r", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-q": FlagSpec("-q", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-9": FlagSpec("-9", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def unzip_contract() -> CommandContract:
    """unzip archive tool"""
    return CommandContract(
        logical_name="unzip",
        description="unzip archive tool",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.READ, ToolEffect.WRITE, ToolEffect.ARCHIVE}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-l": FlagSpec("-l", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-q": FlagSpec("-q", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-d": FlagSpec("-d", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def curl_contract() -> CommandContract:
    """HTTP client"""
    return CommandContract(
        logical_name="curl",
        description="HTTP client",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.NETWORK, ToolEffect.READ}),
                risk=RiskTier.HIGH,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--fail": FlagSpec("--fail", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--silent": FlagSpec("--silent", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--show-error": FlagSpec("--show-error", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--location": FlagSpec("--location", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--max-time": FlagSpec("--max-time", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--header": FlagSpec("--header", takes_value=True, repeatable=True, effects=frozenset({})),
                        },
            ),
        },
    )


def wget_contract() -> CommandContract:
    """HTTP downloader"""
    return CommandContract(
        logical_name="wget",
        description="HTTP downloader",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.NETWORK, ToolEffect.READ, ToolEffect.WRITE}),
                risk=RiskTier.HIGH,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "-q": FlagSpec("-q", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-O": FlagSpec("-O", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--timeout": FlagSpec("--timeout", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def psql_contract() -> CommandContract:
    """PostgreSQL CLI"""
    return CommandContract(
        logical_name="psql",
        description="PostgreSQL CLI",
        default_verb="run",
        verbs={
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.NETWORK, ToolEffect.READ, ToolEffect.WRITE}),
                risk=RiskTier.HIGH,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "-d": FlagSpec("-d", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-h": FlagSpec("-h", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-p": FlagSpec("-p", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-U": FlagSpec("-U", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-c": FlagSpec("-c", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-f": FlagSpec("-f", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


CONTRACT_FACTORIES = (
    jq_contract,
    sqlite3_contract,
    tar_contract,
    zip_contract,
    unzip_contract,
    curl_contract,
    wget_contract,
    psql_contract,
)


def contracts() -> tuple[CommandContract, ...]:
    return tuple(factory() for factory in CONTRACT_FACTORIES)
