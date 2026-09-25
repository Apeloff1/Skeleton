"""Optional interoperability with the OpenAI Agents SDK.

The bridge deliberately does not make the external SDK authoritative for
Skeleton policy, memory, or tool permissions. Only sanitized inputs may cross
this compatibility boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Callable, Iterable, Mapping

from .optional import load_optional
from .registry import source


@dataclass(frozen=True, slots=True)
class ExternalAgentSpec:
    name: str
    instructions: str
    handoff_description: str | None = None
    model: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("agent name must be non-empty")
        if not isinstance(self.instructions, str) or not self.instructions.strip():
            raise ValueError("agent instructions must be non-empty")


@dataclass(frozen=True, slots=True)
class ExternalHandoffSpec:
    tool_name: str | None = None
    tool_description: str | None = None


class AgentsSdkBridge:
    def __init__(
        self,
        *,
        importer: Callable[[str], object] = import_module,
    ) -> None:
        self._importer = importer
        self._module = None

    def _runtime(self):
        if self._module is None:
            self._module = load_optional(
                source("agents-sdk"), "agents", importer=self._importer
            )
        return self._module

    @staticmethod
    def sanitize_context(
        context: Mapping[str, object],
        *,
        allowed_keys: Iterable[str],
    ) -> dict[str, object]:
        allowed = {str(key) for key in allowed_keys}
        return {key: value for key, value in context.items() if key in allowed}

    def create_agent(
        self,
        spec: ExternalAgentSpec,
        *,
        tools: Iterable[object] = (),
    ):
        if not isinstance(spec, ExternalAgentSpec):
            raise TypeError("spec must be ExternalAgentSpec")
        module = self._runtime()
        kwargs: dict[str, object] = {
            "name": spec.name.strip(),
            "instructions": spec.instructions.strip(),
            "tools": list(tools),
        }
        if spec.handoff_description is not None:
            kwargs["handoff_description"] = spec.handoff_description
        if spec.model is not None:
            kwargs["model"] = spec.model
        return module.Agent(**kwargs)

    def create_handoff(
        self,
        target_agent: object,
        spec: ExternalHandoffSpec | None = None,
    ):
        module = self._runtime()
        config = spec or ExternalHandoffSpec()
        kwargs: dict[str, object] = {}
        if config.tool_name is not None:
            kwargs["tool_name_override"] = config.tool_name
        if config.tool_description is not None:
            kwargs["tool_description_override"] = config.tool_description
        return module.handoff(target_agent, **kwargs)

    def guardrail_output(
        self,
        output_info: object,
        *,
        tripwire_triggered: bool,
    ):
        module = self._runtime()
        return module.GuardrailFunctionOutput(
            output_info=output_info,
            tripwire_triggered=bool(tripwire_triggered),
        )


__all__ = [
    "AgentsSdkBridge",
    "ExternalAgentSpec",
    "ExternalHandoffSpec",
]
