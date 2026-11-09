"""Infrastructure typed shell command contracts."""

from __future__ import annotations

from skeleton.shells.contracts.core import CommandContract, FlagSpec, RiskTier, ToolEffect, VerbContract


def docker_contract() -> CommandContract:
    """Docker CLI"""
    return CommandContract(
        logical_name="docker",
        description="Docker CLI",
        default_verb=None,
        verbs={
            "version": VerbContract(
                name="version",
                effects=frozenset({ToolEffect.READ}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=0,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={},
            ),
            "info": VerbContract(
                name="info",
                effects=frozenset({ToolEffect.READ}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=0,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={},
            ),
            "inspect": VerbContract(
                name="inspect",
                effects=frozenset({ToolEffect.READ}),
                risk=RiskTier.LOW,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={},
            ),
            "images": VerbContract(
                name="images",
                effects=frozenset({ToolEffect.READ}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={},
            ),
            "ps": VerbContract(
                name="ps",
                effects=frozenset({ToolEffect.READ}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-a": FlagSpec("-a", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "build": VerbContract(
                name="build",
                effects=frozenset({ToolEffect.READ, ToolEffect.WRITE, ToolEffect.BUILD, ToolEffect.PRIVILEGED}),
                risk=RiskTier.CRITICAL,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "-f": FlagSpec("-f", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-t": FlagSpec("-t", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--pull": FlagSpec("--pull", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.PROCESS, ToolEffect.NETWORK, ToolEffect.PRIVILEGED}),
                risk=RiskTier.CRITICAL,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--rm": FlagSpec("--rm", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-v": FlagSpec("-v", takes_value=True, repeatable=True, effects=frozenset({})),
                            "-p": FlagSpec("-p", takes_value=True, repeatable=True, effects=frozenset({})),
                            "-e": FlagSpec("-e", takes_value=True, repeatable=True, effects=frozenset({})),
                        },
            ),
        },
    )


def podman_contract() -> CommandContract:
    """Podman CLI"""
    return CommandContract(
        logical_name="podman",
        description="Podman CLI",
        default_verb=None,
        verbs={
            "version": VerbContract(
                name="version",
                effects=frozenset({ToolEffect.READ}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=0,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={},
            ),
            "inspect": VerbContract(
                name="inspect",
                effects=frozenset({ToolEffect.READ}),
                risk=RiskTier.LOW,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={},
            ),
            "build": VerbContract(
                name="build",
                effects=frozenset({ToolEffect.READ, ToolEffect.WRITE, ToolEffect.BUILD, ToolEffect.PRIVILEGED}),
                risk=RiskTier.CRITICAL,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "-f": FlagSpec("-f", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-t": FlagSpec("-t", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "run": VerbContract(
                name="run",
                effects=frozenset({ToolEffect.PROCESS, ToolEffect.NETWORK, ToolEffect.PRIVILEGED}),
                risk=RiskTier.CRITICAL,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--rm": FlagSpec("--rm", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-v": FlagSpec("-v", takes_value=True, repeatable=True, effects=frozenset({})),
                            "-p": FlagSpec("-p", takes_value=True, repeatable=True, effects=frozenset({})),
                        },
            ),
        },
    )


def kubectl_contract() -> CommandContract:
    """Kubernetes CLI"""
    return CommandContract(
        logical_name="kubectl",
        description="Kubernetes CLI",
        default_verb=None,
        verbs={
            "get": VerbContract(
                name="get",
                effects=frozenset({ToolEffect.NETWORK, ToolEffect.READ}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "-n": FlagSpec("-n", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-o": FlagSpec("-o", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "describe": VerbContract(
                name="describe",
                effects=frozenset({ToolEffect.NETWORK, ToolEffect.READ}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "-n": FlagSpec("-n", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "logs": VerbContract(
                name="logs",
                effects=frozenset({ToolEffect.NETWORK, ToolEffect.READ}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "-n": FlagSpec("-n", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-c": FlagSpec("-c", takes_value=True, repeatable=False, effects=frozenset({})),
                            "--tail": FlagSpec("--tail", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "apply": VerbContract(
                name="apply",
                effects=frozenset({ToolEffect.NETWORK, ToolEffect.WRITE, ToolEffect.PRIVILEGED}),
                risk=RiskTier.CRITICAL,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "-f": FlagSpec("-f", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-n": FlagSpec("-n", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "delete": VerbContract(
                name="delete",
                effects=frozenset({ToolEffect.NETWORK, ToolEffect.WRITE, ToolEffect.DESTRUCTIVE, ToolEffect.PRIVILEGED}),
                risk=RiskTier.CRITICAL,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "-f": FlagSpec("-f", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-n": FlagSpec("-n", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def helm_contract() -> CommandContract:
    """Helm CLI"""
    return CommandContract(
        logical_name="helm",
        description="Helm CLI",
        default_verb=None,
        verbs={
            "list": VerbContract(
                name="list",
                effects=frozenset({ToolEffect.NETWORK, ToolEffect.READ}),
                risk=RiskTier.MEDIUM,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "-n": FlagSpec("-n", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "status": VerbContract(
                name="status",
                effects=frozenset({ToolEffect.NETWORK, ToolEffect.READ}),
                risk=RiskTier.MEDIUM,
                min_positionals=1,
                max_positionals=1,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "-n": FlagSpec("-n", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
            "template": VerbContract(
                name="template",
                effects=frozenset({ToolEffect.READ}),
                risk=RiskTier.LOW,
                min_positionals=1,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={
                            "-f": FlagSpec("-f", takes_value=True, repeatable=True, effects=frozenset({})),
                            "--set": FlagSpec("--set", takes_value=True, repeatable=True, effects=frozenset({})),
                        },
            ),
            "upgrade": VerbContract(
                name="upgrade",
                effects=frozenset({ToolEffect.NETWORK, ToolEffect.WRITE, ToolEffect.PRIVILEGED}),
                risk=RiskTier.CRITICAL,
                min_positionals=2,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "--install": FlagSpec("--install", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-f": FlagSpec("-f", takes_value=True, repeatable=True, effects=frozenset({})),
                            "-n": FlagSpec("-n", takes_value=True, repeatable=False, effects=frozenset({})),
                        },
            ),
        },
    )


def terraform_contract() -> CommandContract:
    """Terraform CLI"""
    return CommandContract(
        logical_name="terraform",
        description="Terraform CLI",
        default_verb=None,
        verbs={
            "validate": VerbContract(
                name="validate",
                effects=frozenset({ToolEffect.READ}),
                risk=RiskTier.LOW,
                min_positionals=0,
                max_positionals=0,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=False,
                flags={},
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
                            "-check": FlagSpec("-check", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-recursive": FlagSpec("-recursive", takes_value=False, repeatable=False, effects=frozenset({})),
                        },
            ),
            "plan": VerbContract(
                name="plan",
                effects=frozenset({ToolEffect.READ, ToolEffect.NETWORK}),
                risk=RiskTier.HIGH,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "-out": FlagSpec("-out", takes_value=True, repeatable=False, effects=frozenset({})),
                            "-var": FlagSpec("-var", takes_value=True, repeatable=True, effects=frozenset({})),
                        },
            ),
            "apply": VerbContract(
                name="apply",
                effects=frozenset({ToolEffect.WRITE, ToolEffect.NETWORK, ToolEffect.PRIVILEGED}),
                risk=RiskTier.CRITICAL,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "-auto-approve": FlagSpec("-auto-approve", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-var": FlagSpec("-var", takes_value=True, repeatable=True, effects=frozenset({})),
                        },
            ),
            "destroy": VerbContract(
                name="destroy",
                effects=frozenset({ToolEffect.WRITE, ToolEffect.NETWORK, ToolEffect.DESTRUCTIVE, ToolEffect.PRIVILEGED}),
                risk=RiskTier.CRITICAL,
                min_positionals=0,
                max_positionals=None,
                positional_pattern="[^\\x00]{1,4096}",
                requires_approval=True,
                flags={
                            "-auto-approve": FlagSpec("-auto-approve", takes_value=False, repeatable=False, effects=frozenset({})),
                            "-var": FlagSpec("-var", takes_value=True, repeatable=True, effects=frozenset({})),
                        },
            ),
        },
    )


CONTRACT_FACTORIES = (
    docker_contract,
    podman_contract,
    kubectl_contract,
    helm_contract,
    terraform_contract,
)


def contracts() -> tuple[CommandContract, ...]:
    return tuple(factory() for factory in CONTRACT_FACTORIES)
