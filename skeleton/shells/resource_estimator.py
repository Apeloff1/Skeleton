"""Pure resource estimates for shell commands and execution plans."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.execution_plan import ExecutionPlan
from skeleton.shells.runner import ShellCommand, ShellPolicy


@dataclass(frozen=True)
class ResourceEstimate:
    commands: int
    attempts: int
    timeout_seconds: float
    input_bytes: int
    max_output_bytes: int
    environment_bytes: int
    argument_bytes: int

    def __post_init__(self) -> None:
        if any(
            value < 0
            for value in (
                self.commands,
                self.attempts,
                self.timeout_seconds,
                self.input_bytes,
                self.max_output_bytes,
                self.environment_bytes,
                self.argument_bytes,
            )
        ):
            raise ValueError("resource estimate values may not be negative")

    def __add__(self, other: "ResourceEstimate") -> "ResourceEstimate":
        return ResourceEstimate(
            self.commands + other.commands,
            self.attempts + other.attempts,
            self.timeout_seconds + other.timeout_seconds,
            self.input_bytes + other.input_bytes,
            self.max_output_bytes + other.max_output_bytes,
            self.environment_bytes + other.environment_bytes,
            self.argument_bytes + other.argument_bytes,
        )

    def to_dict(self) -> dict[str, int | float]:
        return {
            "commands": self.commands,
            "attempts": self.attempts,
            "timeout_seconds": self.timeout_seconds,
            "input_bytes": self.input_bytes,
            "max_output_bytes": self.max_output_bytes,
            "environment_bytes": self.environment_bytes,
            "argument_bytes": self.argument_bytes,
        }


class ShellResourceEstimator:
    def command(
        self,
        command: ShellCommand,
        policy: ShellPolicy,
        *,
        attempts: int = 1,
    ) -> ResourceEstimate:
        if attempts <= 0:
            raise ValueError("attempts must be positive")
        timeout = command.timeout or policy.default_timeout
        stdin_bytes = 0 if command.stdin is None else len(command.stdin)
        env_bytes = sum(
            len(key.encode("utf-8")) + len(value.encode("utf-8")) + 2
            for key, value in command.env.items()
        )
        arg_bytes = sum(len(value.encode("utf-8")) for value in command.args)
        return ResourceEstimate(
            commands=1,
            attempts=attempts,
            timeout_seconds=timeout * attempts,
            input_bytes=stdin_bytes * attempts,
            max_output_bytes=policy.max_output_bytes * attempts,
            environment_bytes=env_bytes * attempts,
            argument_bytes=arg_bytes * attempts,
        )

    def plan(
        self,
        plan: ExecutionPlan,
        policy: ShellPolicy,
        *,
        attempts_per_step: int = 1,
    ) -> ResourceEstimate:
        total = ResourceEstimate(0, 0, 0, 0, 0, 0, 0)
        for step in plan.steps:
            total = total + self.command(step.command, policy, attempts=attempts_per_step)
        return total
