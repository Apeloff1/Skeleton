"""Version-control typed shell command contracts."""

from __future__ import annotations

from skeleton.shells.contracts.core import CommandContract, FlagSpec, RiskTier, ToolEffect, VerbContract


def git_contract() -> CommandContract:
    """Git version-control operations"""
    return CommandContract(
        logical_name="git",
        description="Git version-control operations",
        default_verb=None,
        verbs={
            "status": VerbContract(
                name="status",
                effects=frozenset({ToolEffect.READ, ToolEffect.VCS}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=0,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--short": FlagSpec("--short", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--porcelain": FlagSpec("--porcelain", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--branch": FlagSpec("--branch", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "diff": VerbContract(
                name="diff",
                effects=frozenset({ToolEffect.READ, ToolEffect.VCS}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--stat": FlagSpec("--stat", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--name-only": FlagSpec("--name-only", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--cached": FlagSpec("--cached", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--check": FlagSpec("--check", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "log": VerbContract(
                name="log",
                effects=frozenset({ToolEffect.READ, ToolEffect.VCS}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--oneline": FlagSpec("--oneline", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--decorate": FlagSpec("--decorate", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--graph": FlagSpec("--graph", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--max-count": FlagSpec("--max-count", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "show": VerbContract(
                name="show",
                effects=frozenset({ToolEffect.READ, ToolEffect.VCS}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=2,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--stat": FlagSpec("--stat", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--name-only": FlagSpec("--name-only", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "add": VerbContract(
                name="add",
                effects=frozenset({ToolEffect.WRITE, ToolEffect.VCS}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--all": FlagSpec("--all", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--intent-to-add": FlagSpec("--intent-to-add", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "restore": VerbContract(
                name="restore",
                effects=frozenset({ToolEffect.WRITE, ToolEffect.VCS}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--staged": FlagSpec("--staged", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--source": FlagSpec("--source", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "commit": VerbContract(
                name="commit",
                effects=frozenset({ToolEffect.WRITE, ToolEffect.VCS}),
                risk=RiskTier.MEDIUM,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-m": FlagSpec("-m", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--message": FlagSpec("--message", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--amend": FlagSpec("--amend", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "branch": VerbContract(
                name="branch",
                effects=frozenset({ToolEffect.WRITE, ToolEffect.VCS}),
                risk=RiskTier.MEDIUM,
                min_positionals=0,
                max_positionals=2,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--list": FlagSpec("--list", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--delete": FlagSpec("--delete", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--force": FlagSpec("--force", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "switch": VerbContract(
                name="switch",
                effects=frozenset({ToolEffect.WRITE, ToolEffect.VCS}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=1,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-c": FlagSpec("-c", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--create": FlagSpec("--create", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "checkout": VerbContract(
                name="checkout",
                effects=frozenset({ToolEffect.WRITE, ToolEffect.VCS}),
                risk=RiskTier.HIGH,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "-b": FlagSpec("-b", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--detach": FlagSpec("--detach", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "merge": VerbContract(
                name="merge",
                effects=frozenset({ToolEffect.WRITE, ToolEffect.VCS}),
                risk=RiskTier.HIGH,
                min_positionals=1,
                max_positionals=1,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--no-ff": FlagSpec("--no-ff", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--ff-only": FlagSpec("--ff-only", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--squash": FlagSpec("--squash", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "rebase": VerbContract(
                name="rebase",
                effects=frozenset({ToolEffect.WRITE, ToolEffect.VCS}),
                risk=RiskTier.HIGH,
                min_positionals=1,
                max_positionals=2,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--abort": FlagSpec("--abort", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--continue": FlagSpec("--continue", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--onto": FlagSpec("--onto", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "reset": VerbContract(
                name="reset",
                effects=frozenset({ToolEffect.WRITE, ToolEffect.VCS, ToolEffect.DESTRUCTIVE}),
                risk=RiskTier.CRITICAL,
                min_positionals=0,
                max_positionals=2,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--soft": FlagSpec("--soft", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--mixed": FlagSpec("--mixed", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--hard": FlagSpec("--hard", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "clean": VerbContract(
                name="clean",
                effects=frozenset({ToolEffect.WRITE, ToolEffect.VCS, ToolEffect.DESTRUCTIVE}),
                risk=RiskTier.CRITICAL,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "-n": FlagSpec("-n", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-d": FlagSpec("-d", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-f": FlagSpec("-f", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-x": FlagSpec("-x", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "fetch": VerbContract(
                name="fetch",
                effects=frozenset({ToolEffect.NETWORK, ToolEffect.VCS}),
                risk=RiskTier.MEDIUM,
                min_positionals=0,
                max_positionals=2,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--all": FlagSpec("--all", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--prune": FlagSpec("--prune", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "pull": VerbContract(
                name="pull",
                effects=frozenset({ToolEffect.NETWORK, ToolEffect.WRITE, ToolEffect.VCS}),
                risk=RiskTier.HIGH,
                min_positionals=0,
                max_positionals=2,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--ff-only": FlagSpec("--ff-only", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--rebase": FlagSpec("--rebase", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "push": VerbContract(
                name="push",
                effects=frozenset({ToolEffect.NETWORK, ToolEffect.WRITE, ToolEffect.VCS}),
                risk=RiskTier.HIGH,
                min_positionals=0,
                max_positionals=3,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--force-with-lease": FlagSpec("--force-with-lease", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--tags": FlagSpec("--tags", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def gh_contract() -> CommandContract:
    """GitHub CLI operations"""
    return CommandContract(
        logical_name="gh",
        description="GitHub CLI operations",
        default_verb=None,
        verbs={
            "pr": VerbContract(
                name="pr",
                effects=frozenset({ToolEffect.READ, ToolEffect.NETWORK, ToolEffect.VCS}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--repo": FlagSpec("--repo", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--json": FlagSpec("--json", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "issue": VerbContract(
                name="issue",
                effects=frozenset({ToolEffect.READ, ToolEffect.NETWORK, ToolEffect.VCS}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--repo": FlagSpec("--repo", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--json": FlagSpec("--json", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.READ, ToolEffect.NETWORK}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--repo": FlagSpec("--repo", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "api": VerbContract(
                name="api",
                effects=frozenset({ToolEffect.NETWORK}),
                risk=RiskTier.HIGH,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--method": FlagSpec("--method", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--field": FlagSpec("--field", takes_value=True, repeatable=True, effects=frozenset({})),
                        },
            ),
        },
    )


def jj_contract() -> CommandContract:
    """Jujutsu version-control operations"""
    return CommandContract(
        logical_name="jj",
        description="Jujutsu version-control operations",
        default_verb=None,
        verbs={
            "status": VerbContract(
                name="status",
                effects=frozenset({ToolEffect.READ, ToolEffect.VCS}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=0,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={},
            ),
            "diff": VerbContract(
                name="diff",
                effects=frozenset({ToolEffect.READ, ToolEffect.VCS}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "--stat": FlagSpec("--stat", takes_value=False, repeatable=False, effects=frozenset({})),
                            "--name-only": FlagSpec("--name-only", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "log": VerbContract(
                name="log",
                effects=frozenset({ToolEffect.READ, ToolEffect.VCS}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-r": FlagSpec("-r", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--limit": FlagSpec("--limit", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "new": VerbContract(
                name="new",
                effects=frozenset({ToolEffect.WRITE, ToolEffect.VCS}),
                risk=RiskTier.MEDIUM,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-m": FlagSpec("-m", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "squash": VerbContract(
                name="squash",
                effects=frozenset({ToolEffect.WRITE, ToolEffect.VCS}),
                risk=RiskTier.HIGH,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "-r": FlagSpec("-r", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def hg_contract() -> CommandContract:
    """Mercurial operations"""
    return CommandContract(
        logical_name="hg",
        description="Mercurial operations",
        default_verb=None,
        verbs={
            "status": VerbContract(
                name="status",
                effects=frozenset({ToolEffect.READ, ToolEffect.VCS}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=0,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={},
            ),
            "diff": VerbContract(
                name="diff",
                effects=frozenset({ToolEffect.READ, ToolEffect.VCS}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={},
            ),
            "log": VerbContract(
                name="log",
                effects=frozenset({ToolEffect.READ, ToolEffect.VCS}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-l": FlagSpec("-l", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "commit": VerbContract(
                name="commit",
                effects=frozenset({ToolEffect.WRITE, ToolEffect.VCS}),
                risk=RiskTier.MEDIUM,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-m": FlagSpec("-m", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "pull": VerbContract(
                name="pull",
                effects=frozenset({ToolEffect.NETWORK, ToolEffect.VCS}),
                risk=RiskTier.MEDIUM,
                min_positionals=0,
                max_positionals=1,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={},
            ),
            "push": VerbContract(
                name="push",
                effects=frozenset({ToolEffect.NETWORK, ToolEffect.WRITE, ToolEffect.VCS}),
                risk=RiskTier.HIGH,
                min_positionals=0,
                max_positionals=1,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={},
            ),
        },
    )


def svn_contract() -> CommandContract:
    """Subversion operations"""
    return CommandContract(
        logical_name="svn",
        description="Subversion operations",
        default_verb=None,
        verbs={
            "status": VerbContract(
                name="status",
                effects=frozenset({ToolEffect.READ, ToolEffect.VCS}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=1,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={},
            ),
            "diff": VerbContract(
                name="diff",
                effects=frozenset({ToolEffect.READ, ToolEffect.VCS}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={},
            ),
            "log": VerbContract(
                name="log",
                effects=frozenset({ToolEffect.READ, ToolEffect.NETWORK, ToolEffect.VCS}),
                risk=RiskTier.MEDIUM,
                min_positionals=0,
                max_positionals=1,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "-l": FlagSpec("-l", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "update": VerbContract(
                name="update",
                effects=frozenset({ToolEffect.NETWORK, ToolEffect.WRITE, ToolEffect.VCS}),
                risk=RiskTier.HIGH,
                min_positionals=0,
                max_positionals=1,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={},
            ),
            "commit": VerbContract(
                name="commit",
                effects=frozenset({ToolEffect.NETWORK, ToolEffect.WRITE, ToolEffect.VCS}),
                risk=RiskTier.HIGH,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "-m": FlagSpec("-m", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


CONTRACT_FACTORIES = (
    git_contract,
    gh_contract,
    jj_contract,
    hg_contract,
    svn_contract,
)


def contracts() -> tuple[CommandContract, ...]:
    return tuple(factory() for factory in CONTRACT_FACTORIES)
