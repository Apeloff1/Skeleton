"""Host-bound Jeeves orchestration over a source-checked local native model.

Only the existing StrictJeevesAgentRuntime may authorize tools. The installed
model is an untrusted proposer; no prompt creates permissions, memory consent
or evidence of a privileged effect.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from .native_provider import NativeJeevesProvider, native_provider_router
from .provider import ProviderRouter
from .runtime import AgentConfig, InMemoryCheckpointer, RunInputs
from .strict_runtime import StrictJeevesAgentRuntime
from .tools import ToolRegistry, ToolExecutor
from .types import AgentResult


class NativeRuntimeHold(ValueError):
    """The principal or operational contract of an agent run is not met."""


def configured_native_agent(
    worker: Any,
    *,
    tools: ToolRegistry | None = None,
    tool_executor: ToolExecutor | None = None,
    checkpointer: InMemoryCheckpointer | None = None,
    config: AgentConfig | None = None,
    runtime_type: type[StrictJeevesAgentRuntime] = StrictJeevesAgentRuntime,
    native_provider: NativeJeevesProvider | None = None,
) -> StrictJeevesAgentRuntime:
    """Construct existing strict Jeeves layers without parallel runtime state.

    Defaults are intentionally conservative for a laptop-sized GGUF. A host
    may provide stronger budgets, but cannot override the canonical native
    output ceiling without reactivating the installed model.
    """
    native = native_provider if native_provider is not None else NativeJeevesProvider(worker)
    if (type(native) is not NativeJeevesProvider
            or native._worker is not worker
            or not native.available()):
        raise NativeRuntimeHold("runtime requires its own checked native provider")
    ceiling = native.capabilities.max_output_tokens
    if config is None:
        config = AgentConfig(
            planner_max_tokens=ceiling,
            step_max_tokens=ceiling,
            verifier_max_tokens=ceiling,
            final_max_tokens=ceiling,
            maximum_plan_steps=4,
            maximum_replans=0,
            grounding_repairs=0,
            enable_model_verification=False,
            verify_read_only_with_model=False,
            stage_memory_candidates=False,
            stage_success_episode=False,
            bridge_verified_evidence=False,
            fail_on_unresolved=True,
        )
    else:
        if any(getattr(config, attr) > ceiling for attr in (
            "planner_max_tokens", "step_max_tokens",
            "verifier_max_tokens", "final_max_tokens",
        )):
            raise NativeRuntimeHold("Jeeves config exceeds real native output limit")
    if not isinstance(runtime_type, type) or not issubclass(runtime_type, StrictJeevesAgentRuntime):
        raise NativeRuntimeHold("strict Jeeves runtime subclass required")
    return runtime_type(
        provider_router=native_provider_router(worker, provider=native),
        tool_registry=tools or ToolRegistry(),
        tool_executor=tool_executor,
        checkpointer=checkpointer,
        config=config,
    )


class NativeJeevesRuntime:
    """Prevent cross-tenant runs and make the admitted agent path explicit."""

    def __init__(
        self,
        worker: Any,
        *,
        tools: ToolRegistry | None = None,
        tool_executor: ToolExecutor | None = None,
        checkpointer: InMemoryCheckpointer | None = None,
        config: AgentConfig | None = None,
        runtime_type: type[StrictJeevesAgentRuntime] = StrictJeevesAgentRuntime,
    ) -> None:
        self.provider = NativeJeevesProvider(worker)
        self.identity = self.provider.identity
        # Exactly one bound native provider and one in-process uncertainty
        # ledger serve both readiness and generation. Canonical SQLite remains
        # the persistent authority for committed or in-flight model calls.
        self.agent = configured_native_agent(
            worker, tools=tools, tool_executor=tool_executor,
            checkpointer=checkpointer, config=config,
            runtime_type=runtime_type, native_provider=self.provider,
        )

    def _validate(self, inputs: RunInputs) -> None:
        if not isinstance(inputs, RunInputs):
            raise NativeRuntimeHold("typed Jeeves RunInputs required")
        if inputs.tenant_id != self.identity.tenant or inputs.user_id != self.identity.subject:
            raise NativeRuntimeHold("cross-principal Jeeves execution denied")
        if inputs.preferred_provider not in (None, self.provider.name):
            raise NativeRuntimeHold("native-only Jeeves cannot use another provider")
        if not self.provider.available():
            raise NativeRuntimeHold("active model identity changed after binding")

    def run(self, inputs: RunInputs) -> AgentResult:
        self._validate(inputs)
        return self.agent.run(inputs)

    def resume_in_process(self, inputs: RunInputs, run_id: str) -> AgentResult:
        """Only same-process checkpoints; not a cold-restart qualification."""
        self._validate(inputs)
        return self.agent.resume(inputs, run_id)

    def cancel_between_calls(self, run_id: str) -> None:
        """Jeeves control-loop cancellation, not native process interruption."""
        self.agent.cancel(run_id)

    def status(self) -> dict[str, object]:
        return {
            "schema": "jeeves.native_agent_status.v1",
            "provider": self.provider.name,
            "model_sha256": self.identity.model_sha256,
            "tokenizer_sha256": self.identity.tokenizer_sha256,
            "principal_bound": self.provider.available(),
            "native_execution_source": "canonical-supervised-ai",
            "restart_safe_model_replay": True,
            "restart_safe_jeeves_checkpoints": False,
            "device_qualified": False,
            "release_certified": False,
        }


__all__ = [
    "NativeRuntimeHold", "NativeJeevesRuntime", "configured_native_agent",
]
